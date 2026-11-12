"""Read-side queries: run lists, event pages, stats rollups, registries."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import Agent, Event, Model, Run
from ..schemas.query import (
    AgentOut,
    ByAgent,
    ByModel,
    EventOut,
    EventsPage,
    ModelOut,
    RunDetail,
    RunSummary,
    StatsResponse,
)
from .aggregates import cost_sum, cost_value, latency_value, tokens_sum, tokens_value

RunCounts = tuple[int, float, int, int]  # event_count, cost_usd, tokens, error_count


def _run_event_aggregates(db: Session, run_ids: list[UUID]) -> dict[UUID, RunCounts]:
    """Aggregate event stats for a bounded set of runs.

    Only the requested runs are summarised, so cost is proportional to the page
    rather than to the whole events table.
    """
    if not run_ids:
        return {}

    rows = db.execute(
        select(
            Event.run_id,
            func.count().label("event_count"),
            cost_sum().label("cost_usd"),
            tokens_sum().label("tokens"),
            func.coalesce(func.sum(case((Event.type == "error", 1), else_=0)), 0).label(
                "error_count"
            ),
        )
        .where(Event.run_id.in_(run_ids))
        .group_by(Event.run_id)
    ).all()

    return {
        row.run_id: (
            int(row.event_count or 0),
            float(row.cost_usd or 0),
            int(row.tokens or 0),
            int(row.error_count or 0),
        )
        for row in rows
    }


def _summary(run: Run, counts: RunCounts) -> RunSummary:
    event_count, cost_usd, tokens, error_count = counts
    return RunSummary(
        id=run.id,
        name=run.name,
        status=run.status,
        schema_version=run.schema_version,
        framework=run.framework,
        started_at=run.started_at,
        finished_at=run.finished_at,
        event_count=event_count,
        cost_usd=cost_usd,
        tokens=tokens,
        error_count=error_count,
    )


_EMPTY_COUNTS: RunCounts = (0, 0.0, 0, 0)


SORT_OPTIONS = frozenset({"recent", "oldest", "name", "cost", "events"})


def _run_filters(status: str | None, q: str | None, framework: str | None) -> list:
    clauses: list = []
    if status:
        clauses.append(Run.status == status)
    if q:
        clauses.append(Run.name.ilike(f"%{q}%"))
    if framework:
        clauses.append(Run.framework == framework)
    return clauses


def list_runs(
    db: Session,
    status: str | None,
    limit: int,
    offset: int,
    q: str | None = None,
    framework: str | None = None,
    sort: str = "recent",
) -> list[RunSummary]:
    stmt = select(Run)
    for clause in _run_filters(status, q, framework):
        stmt = stmt.where(clause)

    if sort in {"cost", "events"}:
        # Order by an event aggregate; one row per run, so no duplication.
        aggregates = (
            select(
                Event.run_id.label("run_id"),
                cost_sum().label("cost_usd"),
                func.count().label("event_count"),
            )
            .group_by(Event.run_id)
            .subquery()
        )
        stmt = stmt.join(aggregates, aggregates.c.run_id == Run.id, isouter=True)
        ordering = aggregates.c.cost_usd if sort == "cost" else aggregates.c.event_count
        stmt = stmt.order_by(ordering.desc().nullslast(), Run.started_at.desc(), Run.id.desc())
    elif sort == "oldest":
        stmt = stmt.order_by(Run.started_at.asc(), Run.id.asc())
    elif sort == "name":
        stmt = stmt.order_by(Run.name.asc().nullslast(), Run.started_at.desc(), Run.id.desc())
    else:
        stmt = stmt.order_by(Run.started_at.desc(), Run.id.desc())

    runs = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    aggregates_by_run = _run_event_aggregates(db, [run.id for run in runs])
    return [_summary(run, aggregates_by_run.get(run.id, _EMPTY_COUNTS)) for run in runs]


def count_runs(
    db: Session,
    status: str | None,
    q: str | None = None,
    framework: str | None = None,
) -> int:
    """Total number of runs (before pagination), honouring every filter."""
    stmt = select(func.count()).select_from(Run)
    for clause in _run_filters(status, q, framework):
        stmt = stmt.where(clause)
    return int(db.execute(stmt).scalar() or 0)


def list_frameworks(db: Session) -> list[str]:
    """Distinct frameworks seen on runs, for the UI's filter select."""
    rows = (
        db.execute(
            select(Run.framework)
            .where(Run.framework.is_not(None))
            .distinct()
            .order_by(Run.framework.asc())
        )
        .scalars()
        .all()
    )
    return [framework for framework in rows if framework]


def get_run(db: Session, run_id: UUID) -> RunDetail | None:
    run = db.get(Run, run_id)
    if run is None:
        return None

    aggregates = _run_event_aggregates(db, [run_id])
    base = _summary(run, aggregates.get(run_id, _EMPTY_COUNTS))
    return RunDetail(
        **base.model_dump(),
        sdk_version=run.sdk_version,
        meta=run.meta or {},
    )


def list_events(db: Session, run_id: UUID, after_seq: int, limit: int) -> EventsPage | None:
    if db.get(Run, run_id) is None:
        return None

    rows = (
        db.execute(
            select(Event)
            .where(Event.run_id == run_id, Event.seq > after_seq)
            .order_by(Event.seq)
            .limit(limit + 1)
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]

    return EventsPage(
        run_id=run_id,
        events=[
            EventOut(
                seq=event.seq,
                ts=event.ts,
                type=event.type,
                from_ref=event.from_ref,
                to_ref=event.to_ref,
                payload=event.payload or {},
            )
            for event in rows
        ],
        next_after_seq=rows[-1].seq if rows else None,
        has_more=has_more,
    )


def build_stats(db: Session, run_id: UUID | None) -> StatsResponse | None:
    if run_id is not None and db.get(Run, run_id) is None:
        return None

    filters = [Event.run_id == run_id] if run_id is not None else []

    totals = db.execute(
        select(
            func.count().label("event_count"),
            cost_sum().label("cost_usd"),
            tokens_sum().label("tokens"),
            func.coalesce(func.sum(case((Event.type == "error", 1), else_=0)), 0).label(
                "error_count"
            ),
            func.avg(case((Event.type == "llm_call", latency_value()), else_=None)).label(
                "avg_latency"
            ),
        ).where(*filters)
    ).one()

    model_rows = db.execute(
        select(
            Event.to_ref.label("model"),
            func.count().label("calls"),
            func.coalesce(func.sum(tokens_value()), 0).label("tokens"),
            func.coalesce(func.sum(cost_value()), 0).label("cost_usd"),
            func.avg(latency_value()).label("avg_latency_ms"),
        )
        .where(Event.type == "llm_call", Event.to_ref.is_not(None), *filters)
        .group_by(Event.to_ref)
        .order_by(func.coalesce(func.sum(cost_value()), 0).desc())
    ).all()

    agent_rows = db.execute(
        select(
            Event.from_ref.label("agent"),
            func.count().label("calls"),
            func.coalesce(func.sum(tokens_value()), 0).label("tokens"),
            func.coalesce(func.sum(cost_value()), 0).label("cost_usd"),
        )
        .where(Event.type == "llm_call", Event.from_ref.is_not(None), *filters)
        .group_by(Event.from_ref)
        .order_by(func.coalesce(func.sum(cost_value()), 0).desc())
    ).all()

    type_rows = db.execute(
        select(Event.type, func.count().label("count"))
        .where(*filters)
        .group_by(Event.type)
        .order_by(Event.type)
    ).all()

    # Count runs, not "runs that happen to have events" — otherwise runs that are still
    # empty disappear from the dashboard while showing up in the runs list.
    if run_id is not None:
        run_count = 1
    else:
        run_count = int(db.execute(select(func.count()).select_from(Run)).scalar() or 0)

    return StatsResponse(
        scope="run" if run_id is not None else "all",
        run_id=run_id,
        event_count=int(totals.event_count or 0),
        run_count=run_count,
        cost_usd=round(float(totals.cost_usd or 0), 8),
        tokens=int(totals.tokens or 0),
        error_count=int(totals.error_count or 0),
        avg_llm_latency_ms=(
            round(float(totals.avg_latency), 2) if totals.avg_latency is not None else None
        ),
        by_type={row.type: int(row.count) for row in type_rows},
        by_model=[
            ByModel(
                model=row.model,
                calls=int(row.calls),
                tokens=int(row.tokens or 0),
                cost_usd=round(float(row.cost_usd or 0), 8),
                avg_latency_ms=(
                    round(float(row.avg_latency_ms), 2) if row.avg_latency_ms is not None else None
                ),
            )
            for row in model_rows
        ],
        by_agent=[
            ByAgent(
                agent=row.agent,
                calls=int(row.calls),
                tokens=int(row.tokens or 0),
                cost_usd=round(float(row.cost_usd or 0), 8),
            )
            for row in agent_rows
        ],
    )


def list_agents(db: Session, limit: int) -> list[AgentOut]:
    rows = db.execute(select(Agent).order_by(Agent.last_seen.desc()).limit(limit)).scalars().all()
    return [
        AgentOut(
            ref=row.ref,
            name=row.name,
            kind=row.kind,
            framework=row.framework,
            first_seen=row.first_seen,
            last_seen=row.last_seen,
        )
        for row in rows
    ]


def list_models(db: Session, limit: int) -> list[ModelOut]:
    rows = db.execute(select(Model).order_by(Model.last_seen.desc()).limit(limit)).scalars().all()
    return [
        ModelOut(
            ref=row.ref,
            provider=row.provider,
            name=row.name,
            first_seen=row.first_seen,
            last_seen=row.last_seen,
        )
        for row in rows
    ]
