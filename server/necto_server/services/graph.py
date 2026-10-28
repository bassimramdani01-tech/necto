"""Graph projection: turn events into nodes and edges (docs/SCHEMA.md §7).

The graph is *computed*, never stored. That keeps storage simple and makes
replay, diffing and topology aggregates fall out for free.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from ..models import Event
from ..schemas.graph import GraphEdge, GraphNode, GraphResponse, GraphStats
from .aggregates import cost_sum, cost_value, latency_value, tokens_sum, tokens_value

# Event types that create a directed edge (from -> to).
EDGE_KINDS = {
    "llm_call": "llm_call",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "handoff": "handoff",
    "message": "message",
    "state_write": "state_write",
}


def _ref_kind(ref: str) -> str:
    return ref.split(":", 1)[0] if ":" in ref else "other"


def _default_name(ref: str) -> str:
    return ref.split(":", 1)[1] if ":" in ref else ref


def _new_node(ref: str) -> dict[str, Any]:
    return {
        "id": ref,
        "kind": _ref_kind(ref),
        "name": None,
        "framework": None,
        "model": None,
        "provider": None,
        "cost_usd": 0.0,
        "tokens": 0,
        "error_count": 0,
        "event_count": 0,
        "first_ts": None,
        "last_ts": None,
    }


def _new_edge(source: str, target: str, kind: str) -> dict[str, Any]:
    return {
        "id": f"{source}->{target}:{kind}",
        "source": source,
        "target": target,
        "kind": kind,
        "count": 0,
        "cost_usd": 0.0,
        "tokens": 0,
        "latency_ms_total": 0,
        "error_count": 0,
        "first_ts": None,
        "last_ts": None,
    }


def _touch(node: dict[str, Any], ts: Any) -> None:
    node["event_count"] += 1
    if node["first_ts"] is None:
        node["first_ts"] = ts
    node["last_ts"] = ts


def _enrich(node: dict[str, Any] | None, event_type: str, payload: dict[str, Any]) -> None:
    """Pull human-readable metadata out of the payloads that carry it."""
    if node is None:
        return
    if event_type == "agent_start" and node["kind"] == "agent":
        node["name"] = payload.get("name") or node["name"]
        node["framework"] = payload.get("framework") or node["framework"]
        node["model"] = payload.get("model") or node["model"]
    elif event_type == "llm_call" and node["kind"] == "model":
        node["name"] = payload.get("model") or node["name"]
        node["provider"] = payload.get("provider") or node["provider"]
    elif event_type == "tool_call" and node["kind"] == "tool":
        node["name"] = payload.get("name") or node["name"]


def project(events: list[Event]) -> tuple[dict[str, dict], dict[str, dict], dict[str, Any]]:
    """Project an ordered list of events into node/edge accumulators."""
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    totals: dict[str, Any] = {
        "event_count": 0,
        "cost_usd": 0.0,
        "tokens": 0,
        "error_count": 0,
        "run_ids": set(),
    }
    # Which edge did a given source most recently emit? Used to attribute errors.
    last_edge_from: dict[str, str] = {}

    for event in events:
        totals["event_count"] += 1
        totals["run_ids"].add(event.run_id)

        payload = event.payload or {}
        source = event.from_ref
        target = event.to_ref
        event_type = event.type

        for ref in (source, target):
            if ref:
                _touch(nodes.setdefault(ref, _new_node(ref)), event.ts)

        _enrich(nodes.get(target) if target else None, event_type, payload)
        _enrich(nodes.get(source) if source else None, event_type, payload)

        if event_type == "error":
            totals["error_count"] += 1
            if source and source in nodes:
                nodes[source]["error_count"] += 1
            previous = last_edge_from.get(source or "")
            if previous and previous in edges:
                edges[previous]["error_count"] += 1
            continue

        if not (source and target) or event_type not in EDGE_KINDS:
            continue

        edge_key = f"{source}->{target}:{event_type}"
        edge = edges.setdefault(edge_key, _new_edge(source, target, event_type))
        edge["count"] += 1
        if edge["first_ts"] is None:
            edge["first_ts"] = event.ts
        edge["last_ts"] = event.ts
        last_edge_from[source] = edge_key

        if event_type == "llm_call":
            tokens = int(payload.get("input_tokens") or 0) + int(payload.get("output_tokens") or 0)
            cost = float(payload.get("cost_usd") or 0.0)
            edge["tokens"] += tokens
            edge["cost_usd"] += cost
            edge["latency_ms_total"] += int(payload.get("latency_ms") or 0)
            totals["tokens"] += tokens
            totals["cost_usd"] += cost
            for ref in (source, target):
                if ref in nodes:
                    nodes[ref]["tokens"] += tokens
                    nodes[ref]["cost_usd"] += cost
        elif event_type == "tool_result":
            edge["latency_ms_total"] += int(payload.get("latency_ms") or 0)

    return nodes, edges, totals


def _finalize(
    nodes: dict[str, dict], edges: dict[str, dict]
) -> tuple[list[GraphNode], list[GraphEdge]]:
    node_list = [
        GraphNode(
            id=node["id"],
            kind=node["kind"],
            name=node["name"] or _default_name(node["id"]),
            framework=node["framework"],
            model=node["model"],
            provider=node["provider"],
            cost_usd=round(node["cost_usd"], 8),
            tokens=node["tokens"],
            error_count=node["error_count"],
            event_count=node["event_count"],
            first_ts=node["first_ts"],
            last_ts=node["last_ts"],
        )
        for node in nodes.values()
    ]
    node_list.sort(key=lambda n: (n.kind, n.id))

    edge_list = []
    for edge in edges.values():
        count = edge["count"] or 1
        edge_list.append(
            GraphEdge(
                id=edge["id"],
                source=edge["source"],
                target=edge["target"],
                kind=edge["kind"],
                count=edge["count"],
                cost_usd=round(edge["cost_usd"], 8),
                tokens=edge["tokens"],
                latency_ms=(edge["latency_ms_total"] // count) if edge["count"] else 0,
                error_count=edge["error_count"],
                error_rate=round(edge["error_count"] / count, 4) if edge["count"] else 0.0,
                first_ts=edge["first_ts"],
                last_ts=edge["last_ts"],
            )
        )
    edge_list.sort(key=lambda e: (e.source, e.target, e.kind))
    return node_list, edge_list


def _response(
    nodes: dict[str, dict],
    edges: dict[str, dict],
    *,
    run_id: UUID | None,
    event_count: int,
    run_count: int,
    cost_usd: float,
    tokens: int,
    error_count: int,
) -> GraphResponse:
    node_list, edge_list = _finalize(nodes, edges)
    return GraphResponse(
        run_id=run_id,
        nodes=node_list,
        edges=edge_list,
        stats=GraphStats(
            node_count=len(node_list),
            edge_count=len(edge_list),
            event_count=event_count,
            run_count=run_count,
            cost_usd=round(cost_usd, 8),
            tokens=tokens,
            error_count=error_count,
        ),
    )


def build_run_graph(db: Session, run_id: UUID) -> GraphResponse:
    events = (
        db.execute(select(Event).where(Event.run_id == run_id).order_by(Event.seq))
        .scalars()
        .all()
    )
    nodes, edges, totals = project(list(events))
    return _response(
        nodes,
        edges,
        run_id=run_id,
        event_count=totals["event_count"],
        run_count=len(totals["run_ids"]),
        cost_usd=totals["cost_usd"],
        tokens=totals["tokens"],
        error_count=totals["error_count"],
    )


# --------------------------------------------------------------------------
# Topology: aggregated in SQL so we never load every event into Python.
# --------------------------------------------------------------------------

_EDGE_TYPES = tuple(EDGE_KINDS)


def _topology_nodes(db: Session) -> dict[str, dict]:
    """Node stats via two grouped passes (as source, then as target)."""
    from_rows = db.execute(
        select(
            Event.from_ref.label("ref"),
            func.count().label("event_count"),
            func.min(Event.ts).label("first_ts"),
            func.max(Event.ts).label("last_ts"),
            cost_sum().label("cost_usd"),
            tokens_sum().label("tokens"),
            func.coalesce(
                func.sum(case((Event.type == "error", 1), else_=0)), 0
            ).label("error_count"),
        )
        .where(Event.from_ref.is_not(None))
        .group_by(Event.from_ref)
    ).all()

    to_rows = db.execute(
        select(
            Event.to_ref.label("ref"),
            func.count().label("event_count"),
            func.min(Event.ts).label("first_ts"),
            func.max(Event.ts).label("last_ts"),
            cost_sum().label("cost_usd"),
            tokens_sum().label("tokens"),
            func.max(
                case(
                    (Event.type == "agent_start", Event.payload["name"].astext),
                    (Event.type == "llm_call", Event.payload["model"].astext),
                    (Event.type == "tool_call", Event.payload["name"].astext),
                    else_=None,
                )
            ).label("name"),
            func.max(
                case(
                    (Event.type == "agent_start", Event.payload["framework"].astext),
                    else_=None,
                )
            ).label("framework"),
            func.max(
                case(
                    (Event.type == "agent_start", Event.payload["model"].astext),
                    else_=None,
                )
            ).label("model"),
            func.max(
                case(
                    (Event.type == "llm_call", Event.payload["provider"].astext),
                    else_=None,
                )
            ).label("provider"),
        )
        .where(Event.to_ref.is_not(None))
        .group_by(Event.to_ref)
    ).all()

    nodes: dict[str, dict] = {}

    def node_for(ref: str) -> dict:
        return nodes.setdefault(ref, _new_node(ref))

    for row in from_rows:
        node = node_for(row.ref)
        node["event_count"] += int(row.event_count or 0)
        node["cost_usd"] += float(row.cost_usd or 0)
        node["tokens"] += int(row.tokens or 0)
        node["error_count"] += int(row.error_count or 0)
        node["first_ts"] = row.first_ts
        node["last_ts"] = row.last_ts

    for row in to_rows:
        node = node_for(row.ref)
        node["event_count"] += int(row.event_count or 0)
        node["cost_usd"] += float(row.cost_usd or 0)
        node["tokens"] += int(row.tokens or 0)
        if row.first_ts is not None and (
            node["first_ts"] is None or row.first_ts < node["first_ts"]
        ):
            node["first_ts"] = row.first_ts
        if row.last_ts is not None and (
            node["last_ts"] is None or row.last_ts > node["last_ts"]
        ):
            node["last_ts"] = row.last_ts
        node["name"] = node["name"] or row.name
        node["framework"] = node["framework"] or row.framework
        node["model"] = node["model"] or row.model
        node["provider"] = node["provider"] or row.provider

    return nodes


def _edge_error_counts(db: Session) -> dict[tuple[str, str, str], int]:
    """Attribute each error to the last edge its source emitted *in the same run*.

    Runs are isolated: an error in one run can never be blamed on another run's
    edge (the old in-memory projection leaked across runs).
    """
    last_edge_seq = (
        func.max(
            case(
                (
                    and_(Event.type.in_(_EDGE_TYPES), Event.to_ref.is_not(None)),
                    Event.seq,
                ),
                else_=None,
            )
        )
        .over(
            partition_by=(Event.run_id, Event.from_ref),
            order_by=Event.seq,
            rows=(None, -1),
        )
        .label("last_edge_seq")
    )

    windowed = (
        select(
            Event.run_id.label("run_id"),
            Event.from_ref.label("from_ref"),
            Event.type.label("type"),
            last_edge_seq,
        ).subquery()
    )

    edge_at = Event.__table__.alias("edge_at")

    rows = db.execute(
        select(
            windowed.c.from_ref.label("source"),
            edge_at.c.to_ref.label("target"),
            edge_at.c.type.label("kind"),
            func.count().label("errors"),
        )
        .select_from(windowed)
        .join(
            edge_at,
            and_(
                edge_at.c.run_id == windowed.c.run_id,
                edge_at.c.seq == windowed.c.last_edge_seq,
            ),
        )
        .where(
            windowed.c.type == "error",
            windowed.c.from_ref.is_not(None),
            windowed.c.last_edge_seq.is_not(None),
        )
        .group_by(windowed.c.from_ref, edge_at.c.to_ref, edge_at.c.type)
    ).all()

    return {(row.source, row.target, row.kind): int(row.errors) for row in rows}


def _topology_edges(db: Session) -> dict[str, dict]:
    rows = db.execute(
        select(
            Event.from_ref.label("source"),
            Event.to_ref.label("target"),
            Event.type.label("kind"),
            func.count().label("count"),
            func.coalesce(
                func.sum(case((Event.type == "llm_call", cost_value()), else_=0)), 0
            ).label("cost_usd"),
            func.coalesce(
                func.sum(case((Event.type == "llm_call", tokens_value()), else_=0)), 0
            ).label("tokens"),
            func.coalesce(
                func.sum(
                    case(
                        (Event.type.in_(("llm_call", "tool_result")), latency_value()),
                        else_=0,
                    )
                ),
                0,
            ).label("latency_total"),
            func.min(Event.ts).label("first_ts"),
            func.max(Event.ts).label("last_ts"),
        )
        .where(
            Event.from_ref.is_not(None),
            Event.to_ref.is_not(None),
            Event.type.in_(_EDGE_TYPES),
        )
        .group_by(Event.from_ref, Event.to_ref, Event.type)
    ).all()

    edges: dict[str, dict] = {}
    for row in rows:
        edge = _new_edge(row.source, row.target, row.kind)
        edge["count"] = int(row.count or 0)
        edge["cost_usd"] = float(row.cost_usd or 0)
        edge["tokens"] = int(row.tokens or 0)
        edge["latency_ms_total"] = int(row.latency_total or 0)
        edge["first_ts"] = row.first_ts
        edge["last_ts"] = row.last_ts
        edges[edge["id"]] = edge

    for (source, target, kind), errors in _edge_error_counts(db).items():
        key = f"{source}->{target}:{kind}"
        if key in edges:
            edges[key]["error_count"] += errors

    return edges


def build_topology(db: Session) -> GraphResponse:
    totals = db.execute(
        select(
            func.count().label("event_count"),
            func.count(func.distinct(Event.run_id)).label("run_count"),
            cost_sum().label("cost_usd"),
            tokens_sum().label("tokens"),
            func.coalesce(
                func.sum(case((Event.type == "error", 1), else_=0)), 0
            ).label("error_count"),
        )
    ).one()

    return _response(
        _topology_nodes(db),
        _topology_edges(db),
        run_id=None,
        event_count=int(totals.event_count or 0),
        run_count=int(totals.run_count or 0),
        cost_usd=float(totals.cost_usd or 0),
        tokens=int(totals.tokens or 0),
        error_count=int(totals.error_count or 0),
    )

