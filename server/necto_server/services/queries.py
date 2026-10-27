"""Read-side queries: run lists, event pages, stats rollups, registries."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Integer, Numeric, case, cast, func, select
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


def _cost_value():
    return cast(Event.payload["cost_usd"].astext, Numeric(18, 8))


def _tokens_value():
    return func.coalesce(
        cast(Event.payload["input_tokens"].astext, Integer), 0
    ) + func.coalesce(cast(Event.payload["output_tokens"].astext, Integer), 0)


def _latency_value():
    return cast(Event.payload["latency_ms"].astext, Integer)


def _cost_sum():
    return func.coalesce(
        func.sum(case((Event.type == "llm_call", _cost_value()), else_=0)), 0
    )


def _tokens_sum():
    return func.coalesce(
        func.sum(case((Event.type == "llm_call", _tokens_value()), else_=0)), 0
    )


def _summary_subquery():
    return (
        select(
            Event.run_id.label("run_id"),
            func.count().label("event_count"),
            _cost_sum().label("cost_usd"),
            _tokens_sum().label("tokens"),
            func.coalesce(
                func.sum(case((Event.type == "error", 1), else_=0)), 0
            ).label("error_count"),
        )
        .group_by(Event.run_id)
        .subquery()
    )


def _summary(run: Run, event_count, cost_usd, tokens, error_count) -> RunSummary:
    return RunSummary(
        id=run.id,
        name=run.name,
        status=run.status,
        schema_version=run.schema_version,
        framework=run.framework,
        started_at=run.started_at,
        finished_at=run.finished_at,
        event_count=int(event_count or 0),
        cost_usd=float(cost_usd or 0),
        tokens=int(tokens or 0),
        error_count=int(error_count or 0),
    )


def list_runs(
    db: Session, status: str | None, limit: int, offset: int
) -> list[RunSummary]:
    summary = _summary_subquery()
    stmt = (
        select(
            Run,
            summary.c.event_count,
            summary.c.cost_usd,
            summary.c.tokens,
            summary.c.error_count,
        )
        .outerjoin(summary, summary.c.run_id == Run.id)
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(Run.status == status)

    rows = db.execute(stmt).all()
    return [
        _summary(run, event_count, cost_usd, tokens, error_count)
        for run, event_count, cost_usd, tokens, error_count in rows
    ]


def get_run(db: Session, run_id: UUID) -> RunDetail | None:
    summary = _summary_subquery()
    row = db.execute(
        select(
            Run,
            summary.c.event_count,
            summary.c.cost_usd,
            summary.c.tokens,
            summary.c.error_count,
        )
        .outerjoin(summary, summary.c.run_id == Run.id)
        .where(Run.id == run_id)
    ).first()
    if row is None:
        return None

    run, event_count, cost_usd, tokens, error_count = row
    base = _summary(run, event_count, cost_usd, tokens, error_count)
    return RunDetail(
        **base.model_dump(),
        sdk_version=run.sdk_version,
        meta=run.meta or {},
    )


def list_events(
    db: Session, run_id: UUID, after_seq: int, limit: int
) -> EventsPage | None:
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
            _cost_sum().label("cost_usd"),
            _tokens_sum().label("tokens"),
            func.coalesce(
                func.sum(case((Event.type == "error", 1), else_=0)), 0
            ).label("error_count"),
            func.count(func.distinct(Event.run_id)).label("run_count"),
            func.avg(
                case((Event.type == "llm_call", _latency_value()), else_=None)
            ).label("avg_latency"),
        ).where(*filters)
    ).one()

    model_rows = db.execute(
        select(
            Event.to_ref.label("model"),
            func.count().label("calls"),
            func.coalesce(func.sum(_tokens_value()), 0).label("tokens"),
            func.coalesce(func.sum(_cost_value()), 0).label("cost_usd"),
            func.avg(_latency_value()).label("avg_latency_ms"),
        )
        .where(Event.type == "llm_call", *filters)
        .group_by(Event.to_ref)
        .order_by(func.coalesce(func.sum(_cost_value()), 0).desc())
    ).all()

    agent_rows = db.execute(
        select(
            Event.from_ref.label("agent"),
            func.count().label("calls"),
            func.coalesce(func.sum(_tokens_value()), 0).label("tokens"),
            func.coalesce(func.sum(_cost_value()), 0).label("cost_usd"),
        )
        .where(Event.type == "llm_call", *filters)
        .group_by(Event.from_ref)
        .order_by(func.coalesce(func.sum(_cost_value()), 0).desc())
    ).all()

    type_rows = db.execute(
        select(Event.type, func.count().label("count"))
        .where(*filters)
        .group_by(Event.type)
        .order_by(Event.type)
    ).all()

    return StatsResponse(
        scope="run" if run_id is not None else "all",
        run_id=run_id,
        event_count=int(totals.event_count or 0),
        run_count=int(totals.run_count or 0),
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
                    round(float(row.avg_latency_ms), 2)
                    if row.avg_latency_ms is not None
                    else None
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
    rows = (
        db.execute(select(Agent).order_by(Agent.last_seen.desc()).limit(limit))
        .scalars()
        .all()
    )
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
    rows = (
        db.execute(select(Model).order_by(Model.last_seen.desc()).limit(limit))
        .scalars()
        .all()
    )
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
