"""Ingestion logic: run lifecycle, event validation, sequence assignment."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Agent, Event, Model, Run
from ..schemas.events import (
    MAX_EVENT_BYTES,
    MAX_SNIPPET_CHARS,
    PAYLOAD_MODELS,
    EventBatch,
    RunFinishIn,
)


def _truncate_strings(value: Any, limit: int) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit]
    if isinstance(value, dict):
        return {k: _truncate_strings(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate_strings(v, limit) for v in value]
    return value


def prepare_payload(payload: dict[str, Any], store_full: bool) -> dict[str, Any]:
    """Apply schema §6 truncation unless the run opted into full retention."""
    if store_full:
        return payload
    return _truncate_strings(payload, MAX_SNIPPET_CHARS)


def _event_size(event: Any) -> int:
    as_dict = event.model_dump(by_alias=True, mode="json")
    return len(json.dumps(as_dict, ensure_ascii=False).encode("utf-8"))


def validate_events(batch: EventBatch) -> None:
    for event in batch.events:
        if event.schema_version > settings.schema_version:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"unsupported schema_version {event.schema_version}; "
                    f"server supports up to {settings.schema_version}"
                ),
            )
        if _event_size(event) > MAX_EVENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"event exceeds the {MAX_EVENT_BYTES} byte limit",
            )

        model = PAYLOAD_MODELS.get(event.type)
        if model is None:
            continue  # unknown types are tolerated (schema §2)
        try:
            model.model_validate(event.payload)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=[
                    {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
                    for err in exc.errors()
                ],
            ) from exc


def _collect_agents(events) -> list[dict[str, Any]]:
    """Gather agent refs seen in a batch, with their display metadata."""
    entries: dict[str, dict[str, Any]] = {}
    for event in events:
        payload = event.payload or {}
        for ref in (event.from_ref, event.to_ref):
            if not ref or not ref.startswith("agent:"):
                continue
            entry = entries.setdefault(
                ref,
                {
                    "ref": ref,
                    "kind": "agent",
                    "name": None,
                    "framework": None,
                    "first_seen": event.ts,
                    "last_seen": event.ts,
                },
            )
            entry["last_seen"] = event.ts
            if event.type == "agent_start" and event.to_ref == ref:
                entry["name"] = payload.get("name") or entry["name"]
                entry["framework"] = payload.get("framework") or entry["framework"]
    return list(entries.values())


def _collect_models(events) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.type != "llm_call" or not event.to_ref:
            continue
        if not event.to_ref.startswith("model:"):
            continue
        payload = event.payload or {}
        entry = entries.setdefault(
            event.to_ref,
            {
                "ref": event.to_ref,
                "provider": None,
                "name": None,
                "first_seen": event.ts,
                "last_seen": event.ts,
            },
        )
        entry["last_seen"] = event.ts
        entry["provider"] = payload.get("provider") or entry["provider"]
        entry["name"] = payload.get("model") or entry["name"]
    return list(entries.values())


def _register_registries(db: Session, events) -> None:
    """Upsert the agents/models registries (docs/ARCHITECTURE.md §5)."""
    agent_rows = _collect_agents(events)
    if agent_rows:
        stmt = pg_insert(Agent).values(agent_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ref"],
            set_={
                "name": func.coalesce(stmt.excluded.name, Agent.name),
                "framework": func.coalesce(stmt.excluded.framework, Agent.framework),
                "last_seen": func.greatest(Agent.last_seen, stmt.excluded.last_seen),
            },
        )
        db.execute(stmt)

    model_rows = _collect_models(events)
    if model_rows:
        stmt = pg_insert(Model).values(model_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ref"],
            set_={
                "provider": func.coalesce(stmt.excluded.provider, Model.provider),
                "name": func.coalesce(stmt.excluded.name, Model.name),
                "last_seen": func.greatest(Model.last_seen, stmt.excluded.last_seen),
            },
        )
        db.execute(stmt)


def create_run(
    db: Session, name: str | None, meta: dict[str, Any], schema_version: int
) -> Run:
    if schema_version > settings.schema_version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"unsupported schema_version {schema_version}; "
                f"server supports up to {settings.schema_version}"
            ),
        )
    run = Run(name=name, meta=meta, schema_version=schema_version, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def append_events(db: Session, run_id: UUID, batch: EventBatch) -> tuple[int, int]:
    validate_events(batch)

    run = db.execute(
        select(Run).where(Run.id == run_id).with_for_update()
    ).scalar_one_or_none()
    if run is None:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    if run.status != "running":
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run status is '{run.status}'; events can only be appended to running runs",
        )

    run_meta = dict(run.meta or {})
    store_full = bool(run_meta.get("store_full"))

    # A run_start event may opt the run into full payload retention.
    for event in batch.events:
        meta = event.payload.get("meta")
        if event.type == "run_start" and isinstance(meta, dict) and meta.get("store_full"):
            store_full = True
            run_meta["store_full"] = True
    if store_full:
        run.meta = run_meta

    last_seq = db.execute(
        select(func.max(Event.seq)).where(Event.run_id == run_id)
    ).scalar() or 0

    for offset, event in enumerate(batch.events, start=1):
        db.add(
            Event(
                run_id=run_id,
                seq=last_seq + offset,
                ts=event.ts,
                type=event.type,
                from_ref=event.from_ref,
                to_ref=event.to_ref,
                payload=prepare_payload(event.payload, store_full),
            )
        )

    _register_registries(db, batch.events)

    accepted = len(batch.events)
    db.commit()
    return accepted, last_seq + accepted


def finish_run(db: Session, run_id: UUID, body: RunFinishIn) -> Run:
    run = db.execute(
        select(Run).where(Run.id == run_id).with_for_update()
    ).scalar_one_or_none()
    if run is None:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")

    run.status = body.status
    run.finished_at = datetime.now(timezone.utc)

    meta = dict(run.meta or {})
    if body.output is not None:
        meta["final_output"] = body.output[:MAX_SNIPPET_CHARS]
    if body.duration_ms is not None:
        meta["duration_ms"] = body.duration_ms
    run.meta = meta

    db.commit()
    db.refresh(run)
    return run
