"""Graph endpoints: per-run graph and aggregate system topology."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Run
from ..schemas.graph import GraphResponse
from ..services import graph

router = APIRouter(prefix="/v1", tags=["graph"])


@router.get("/runs/{run_id}/graph", response_model=GraphResponse)
def run_graph(run_id: UUID, db: Session = Depends(get_db)) -> GraphResponse:
    if db.get(Run, run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return graph.build_run_graph(db, run_id)


@router.get("/topology", response_model=GraphResponse)
def topology(db: Session = Depends(get_db)) -> GraphResponse:
    return graph.build_topology(db)
