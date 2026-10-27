"""Ingestion endpoints: create run, append events, finish run."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.events import (
    EventBatch,
    EventsAccepted,
    RunCreate,
    RunCreated,
    RunFinishIn,
    RunFinished,
)
from ..services import ingestion

router = APIRouter(prefix="/v1", tags=["ingestion"])


@router.post("/runs", status_code=201, response_model=RunCreated)
def create_run(body: RunCreate, db: Session = Depends(get_db)) -> RunCreated:
    run = ingestion.create_run(db, body.name, body.meta, body.schema_version)
    return RunCreated(id=run.id, status=run.status, schema_version=run.schema_version)


@router.post("/runs/{run_id}/events", response_model=EventsAccepted)
def append_events(
    run_id: UUID, batch: EventBatch, db: Session = Depends(get_db)
) -> EventsAccepted:
    accepted, last_seq = ingestion.append_events(db, run_id, batch)
    return EventsAccepted(accepted=accepted, last_seq=last_seq)


@router.post("/runs/{run_id}/finish", response_model=RunFinished)
def finish_run(
    run_id: UUID, body: RunFinishIn, db: Session = Depends(get_db)
) -> RunFinished:
    run = ingestion.finish_run(db, run_id, body)
    return RunFinished(id=run.id, status=run.status, finished=True)
