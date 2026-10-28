"""In-process pub/sub hub for live run streaming (single-node MVP).

Subscribers are asyncio queues keyed by run id. Publishing happens from sync
request handlers (threadpool threads), so messages are handed to the event loop
thread-safely via loop.call_soon_threadsafe().
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import Any
from uuid import UUID

MAX_QUEUE_SIZE = 256


class LiveHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the app's event loop so sync code can publish to it."""
        self._loop = loop

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(run_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(run_id, None)

    def subscriber_count(self, run_id: str) -> int:
        return len(self._subscribers.get(run_id, ()))

    @staticmethod
    def _deliver(queue: asyncio.Queue, message: dict[str, Any]) -> None:
        """Never block: if a slow client fills its queue, drop the oldest."""
        try:
            queue.put_nowait(message)
            return
        except asyncio.QueueFull:
            pass
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(message)

    def publish(self, run_id: str, message: dict[str, Any]) -> int:
        """Fan a message out to every subscriber of a run. Returns recipient count."""
        subscribers = self._subscribers.get(run_id)
        if not subscribers:
            return 0

        loop = self._loop
        use_loop = loop is not None and loop.is_running()
        for queue in list(subscribers):
            if use_loop:
                loop.call_soon_threadsafe(self._deliver, queue, message)
            else:
                self._deliver(queue, message)
        return len(subscribers)


hub = LiveHub()


def publish_events(run_id: UUID, events: list[dict[str, Any]]) -> None:
    hub.publish(
        str(run_id),
        {"type": "events", "run_id": str(run_id), "events": events},
    )


def publish_finished(run_id: UUID, status: str, finished_at: datetime | None) -> None:
    hub.publish(
        str(run_id),
        {
            "type": "run_finished",
            "run_id": str(run_id),
            "status": status,
            "finished_at": finished_at.isoformat() if finished_at else None,
        },
    )
