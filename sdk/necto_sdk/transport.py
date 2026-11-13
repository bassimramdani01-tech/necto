"""Transports for shipping events to a necto server.

The SDK ships with three:
- HttpTransport      — talks to a running necto server (stdlib only)
- RecordingTransport — keeps everything in memory (tests / dry runs)
- NullTransport      — drops everything (necto disabled)
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0
DEFAULT_ATTEMPTS = 2
DEFAULT_BACKOFF = 0.25
# Never let a server's Retry-After stall the host app for longer than this.
MAX_RETRY_AFTER = 30.0


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    """Parse a 429 Retry-After header (seconds or HTTP-date)."""
    headers = getattr(exc, "headers", None)
    raw = headers.get("Retry-After") if headers is not None else None
    if not raw:
        return None
    value = str(raw).strip()
    try:
        return max(0.0, float(int(value)))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


class Transport(Protocol):
    def create_run(self, name: str | None, meta: dict[str, Any]) -> str | None: ...

    def append_events(self, run_id: str, events: list[dict[str, Any]]) -> None: ...

    def finish_run(self, run_id: str, status: str, output: str | None) -> None: ...


class RecordingTransport:
    """Keeps every call in memory — useful for tests and dry runs."""

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.finished: list[dict[str, Any]] = []

    def create_run(self, name: str | None, meta: dict[str, Any]) -> str | None:
        run_id = f"rec-{len(self.runs) + 1}"
        self.runs.append({"id": run_id, "name": name, "meta": meta})
        return run_id

    def append_events(self, run_id: str, events: list[dict[str, Any]]) -> None:
        self.events.setdefault(run_id, []).extend(events)

    def finish_run(self, run_id: str, status: str, output: str | None) -> None:
        self.finished.append({"id": run_id, "status": status, "output": output})

    # convenience for assertions
    def all_events(self) -> list[dict[str, Any]]:
        return [event for events in self.events.values() for event in events]


class NullTransport:
    """Drops everything. Returns no run id, which makes the tracer a no-op."""

    def create_run(self, name: str | None, meta: dict[str, Any]) -> str | None:
        return None

    def append_events(self, run_id: str, events: list[dict[str, Any]]) -> None:
        return None

    def finish_run(self, run_id: str, status: str, output: str | None) -> None:
        return None


class HttpTransport:
    """POSTs to a necto server. Never raises: failures are logged and dropped."""

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        attempts: int = DEFAULT_ATTEMPTS,
        backoff: float = DEFAULT_BACKOFF,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.attempts = max(1, int(attempts))
        self.backoff = max(0.0, float(backoff))

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(f"{self.endpoint}{path}", data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.api_key:
            request.add_header("X-API-Key", self.api_key)

        for attempt in range(1, self.attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")[:500]
                except Exception:  # noqa: BLE001
                    detail = "<no body>"
                logger.warning(
                    "necto: %s %s -> HTTP %s (attempt %s/%s): %s",
                    method,
                    path,
                    exc.code,
                    attempt,
                    self.attempts,
                    detail,
                )
                # 429 is the one 4xx worth retrying — respect Retry-After when present.
                if exc.code == 429:
                    if attempt >= self.attempts:
                        return None
                    delay = _retry_after_seconds(exc)
                    if delay is None:
                        delay = self.backoff * attempt
                    time.sleep(min(max(delay, 0.0), MAX_RETRY_AFTER))
                    continue
                # Any other 4xx means we sent something wrong; retrying cannot help.
                if 400 <= exc.code < 500:
                    return None
            except Exception as exc:  # noqa: BLE001 - transport must never break the host app
                logger.warning(
                    "necto: %s %s failed (attempt %s/%s): %s",
                    method,
                    path,
                    attempt,
                    self.attempts,
                    exc,
                )
            if attempt < self.attempts:
                time.sleep(self.backoff * attempt)
        return None

    def create_run(self, name: str | None, meta: dict[str, Any]) -> str | None:
        body = {"name": name, "meta": meta}
        result = self._request("POST", "/v1/runs", body)
        return result.get("id") if isinstance(result, dict) else None

    def append_events(self, run_id: str, events: list[dict[str, Any]]) -> None:
        if not run_id:
            return
        self._request("POST", f"/v1/runs/{run_id}/events", {"events": events})

    def finish_run(self, run_id: str, status: str, output: str | None) -> None:
        if not run_id:
            return
        self._request("POST", f"/v1/runs/{run_id}/finish", {"status": status, "output": output})
