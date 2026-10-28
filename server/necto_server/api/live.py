"""WebSocket endpoint for live run streaming."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select

from ..auth import check_api_key
from ..db import SessionLocal
from ..models import Event, Run
from ..services import live

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live"])

HEARTBEAT_SECONDS = 30


def _load_run_state(run_id: UUID) -> dict | None:
    """Load just what the socket needs, then close the session."""
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run is None:
            return None
        last_seq = (
            db.execute(select(func.max(Event.seq)).where(Event.run_id == run_id)).scalar() or 0
        )
        return {"status": run.status, "last_seq": int(last_seq)}


def _only_new_events(message: dict, last_seq: int) -> dict | None:
    """Drop events already covered by the hello's last_seq.

    Events can be published between subscribe() and the state read, so they may
    show up both in last_seq and in the queue. Keep only the ones beyond last_seq.
    """
    if message.get("type") != "events":
        return message
    fresh = [event for event in message.get("events", []) if event.get("seq", 0) > last_seq]
    if not fresh:
        return None
    return {**message, "events": fresh}


async def _drain_pending(websocket: WebSocket, queue: asyncio.Queue, last_seq: int) -> None:
    """Forward whatever arrived between subscribe and hello, minus duplicates."""
    while True:
        try:
            pending = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        filtered = _only_new_events(pending, last_seq)
        if filtered is not None:
            await websocket.send_json(filtered)


@router.websocket("/v1/live/runs/{run_id}")
async def live_run(websocket: WebSocket, run_id: UUID) -> None:
    await websocket.accept()

    if not check_api_key(websocket.headers.get("x-api-key")):
        await websocket.close(code=4401, reason="missing or invalid API key")
        return

    # Subscribe BEFORE reading state. Reading last_seq first left a window where
    # events published in between were sent to nobody and silently lost.
    live.hub.bind_loop(asyncio.get_running_loop())
    queue = live.hub.subscribe(str(run_id))

    try:
        state = await run_in_threadpool(_load_run_state, run_id)
        if state is None:
            await websocket.close(code=4404, reason="run not found")
            return

        last_seq = state["last_seq"]
        await websocket.send_json(
            {
                "type": "hello",
                "run_id": str(run_id),
                "run_status": state["status"],
                "last_seq": last_seq,
            }
        )

        await _drain_pending(websocket, queue, last_seq)

        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("live socket failed for run %s", run_id)
    finally:
        live.hub.unsubscribe(str(run_id), queue)
