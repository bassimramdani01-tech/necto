"""WebSocket endpoint for live run streaming."""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select

from ..db import SessionLocal
from ..models import Event, Run
from ..services import live

router = APIRouter(tags=["live"])

HEARTBEAT_SECONDS = 30


def _load_run_state(run_id: UUID) -> dict | None:
    """Load just what the socket needs, then close the session."""
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run is None:
            return None
        last_seq = (
            db.execute(select(func.max(Event.seq)).where(Event.run_id == run_id)).scalar()
            or 0
        )
        return {"status": run.status, "last_seq": int(last_seq)}


@router.websocket("/v1/live/runs/{run_id}")
async def live_run(websocket: WebSocket, run_id: UUID) -> None:
    state = await run_in_threadpool(_load_run_state, run_id)
    await websocket.accept()

    if state is None:
        await websocket.close(code=4404, reason="run not found")
        return

    live.hub.bind_loop(asyncio.get_running_loop())
    queue = live.hub.subscribe(str(run_id))
    try:
        await websocket.send_json(
            {
                "type": "hello",
                "run_id": str(run_id),
                "run_status": state["status"],
                "last_seq": state["last_seq"],
            }
        )
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Client vanished mid-send; drop the subscription quietly.
        pass
    finally:
        live.hub.unsubscribe(str(run_id), queue)
