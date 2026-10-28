"""Read endpoints: runs, events, stats, agent/model registries."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..schemas.query import (
    AgentOut,
    EventsPage,
    ModelOut,
    RunDetail,
    RunSummary,
    StatsResponse,
)
from ..services import queries

router = APIRouter(prefix="/v1", tags=["query"], dependencies=[Depends(require_api_key)])


@router.get("/runs", response_model=list[RunSummary])
def list_runs(
    response: Response,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[RunSummary]:
    # Total (before pagination) so clients can render "page 2 of 7".
    response.headers["X-Total-Count"] = str(queries.count_runs(db, status))
    return queries.list_runs(db, status=status, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: UUID, db: Session = Depends(get_db)) -> RunDetail:
    detail = queries.get_run(db, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    return detail


@router.get("/runs/{run_id}/events", response_model=EventsPage)
def list_events(
    run_id: UUID,
    after_seq: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> EventsPage:
    page = queries.list_events(db, run_id, after_seq=after_seq, limit=limit)
    if page is None:
        raise HTTPException(status_code=404, detail="run not found")
    return page


@router.get("/stats", response_model=StatsResponse)
def stats(run_id: UUID | None = None, db: Session = Depends(get_db)) -> StatsResponse:
    result = queries.build_stats(db, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result


@router.get("/agents", response_model=list[AgentOut])
def list_agents(
    limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)
) -> list[AgentOut]:
    return queries.list_agents(db, limit=limit)


@router.get("/models", response_model=list[ModelOut])
def list_models(
    limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)
) -> list[ModelOut]:
    return queries.list_models(db, limit=limit)
