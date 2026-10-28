"""Ingestion endpoints: create run, append events, finish run."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..schemas.events import (
    EventBatch,
    EventsAccepted,
    RunCreate,
    RunCreated,
    RunFinished,
    RunFinishIn,
)
from ..services import ingestion, live

router = APIRouter(prefix="/v1", tags=["ingestion"], dependencies=[Depends(require_api_key)])


@router.post("/runs", status_code=201, response_model=RunCreated)
def create_run(body: RunCreate, db: Session = Depends(get_db)) -> RunCreated:
    run = ingestion.create_run(db, body.name, body.meta, body.schema_version)
    return RunCreated(id=run.id, status=run.status, schema_version=run.schema_version)


@router.post("/runs/{run_id}/events", response_model=EventsAccepted)
def append_events(run_id: UUID, batch: EventBatch, db: Session = Depends(get_db)) -> EventsAccepted:
    accepted, last_seq, stored = ingestion.append_events(db, run_id, batch)
    live.publish_events(run_id, stored)
    return EventsAccepted(accepted=accepted, last_seq=last_seq)


@router.post("/runs/{run_id}/finish", response_model=RunFinished)
def finish_run(run_id: UUID, body: RunFinishIn, db: Session = Depends(get_db)) -> RunFinished:
    run = ingestion.finish_run(db, run_id, body)
    live.publish_finished(run_id, run.status, run.finished_at)
    return RunFinished(id=run.id, status=run.status, finished=True)
