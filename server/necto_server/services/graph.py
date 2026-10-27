"""Graph projection: turn events into nodes and edges (docs/SCHEMA.md §7).

The graph is *computed*, never stored. That keeps storage simple and makes
replay, diffing and topology aggregates fall out for free.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Event
from ..schemas.graph import GraphEdge, GraphNode, GraphResponse, GraphStats

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
    nodes: dict[str, dict], edges: dict[str, dict], totals: dict[str, Any], run_id: UUID | None
) -> GraphResponse:
    node_list, edge_list = _finalize(nodes, edges)
    return GraphResponse(
        run_id=run_id,
        nodes=node_list,
        edges=edge_list,
        stats=GraphStats(
            node_count=len(node_list),
            edge_count=len(edge_list),
            event_count=totals["event_count"],
            run_count=len(totals["run_ids"]),
            cost_usd=round(totals["cost_usd"], 8),
            tokens=totals["tokens"],
            error_count=totals["error_count"],
        ),
    )


def build_run_graph(db: Session, run_id: UUID) -> GraphResponse:
    events = (
        db.execute(select(Event).where(Event.run_id == run_id).order_by(Event.seq))
        .scalars()
        .all()
    )
    nodes, edges, totals = project(list(events))
    return _response(nodes, edges, totals, run_id)


def build_topology(db: Session) -> GraphResponse:
    events = (
        db.execute(select(Event).order_by(Event.run_id, Event.seq)).scalars().all()
    )
    nodes, edges, totals = project(list(events))
    return _response(nodes, edges, totals, None)
