"""The necto tracer: buffered, non-blocking, never crashes the host app."""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from .events import agent as agent_ref
from .events import model as model_ref
from .events import tool as tool_ref
from .events import event as make_event
from .transport import HttpTransport, NullTransport, Transport

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 64
DEFAULT_FLUSH_INTERVAL = 1.0


class Run:
    """A single observed run. Emit events through its convenience methods."""

    def __init__(self, tracer: Necto, run_id: str | None) -> None:
        self._tracer = tracer
        self.run_id = run_id
        self.disabled = run_id is None
        self._finished = False

    # -- low level ---------------------------------------------------------
    def emit(
        self,
        type: str,
        payload: dict[str, Any] | None = None,
        from_ref: str | None = None,
        to_ref: str | None = None,
        ts: str | None = None,
    ) -> dict[str, Any] | None:
        if self.disabled:
            return None
        event = make_event(type, payload, from_ref, to_ref, ts)
        self._tracer._append(self.run_id, event)  # noqa: SLF001 - internal by design
        return event

    # -- lifecycle ---------------------------------------------------------
    def run_start(self, input_text: str, meta: dict[str, Any] | None = None) -> None:
        self.emit("run_start", {"input": input_text, "meta": meta or {}})

    def run_finish(self, status: str = "ok", output: str | None = None) -> None:
        self.emit("run_finish", {"status": status, "output": output})

    def finish(self, status: str = "ok", output: str | None = None) -> None:
        """Flush and mark the run finished (idempotent)."""
        if self._finished or self.disabled:
            return
        self._finished = True
        self._tracer.flush()
        self._tracer._safe(self._tracer._transport.finish_run, self.run_id, status, output)  # noqa: SLF001

    # -- agents ------------------------------------------------------------
    def agent_start(
        self,
        agent_id: str,
        name: str | None = None,
        framework: str | None = None,
        model: str | None = None,
        input_snippet: str | None = None,
        from_ref: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"name": name or agent_id}
        if framework is not None:
            payload["framework"] = framework
        if model is not None:
            payload["model"] = model
        if input_snippet is not None:
            payload["input_snippet"] = input_snippet
        self.emit("agent_start", payload, from_ref=from_ref, to_ref=agent_ref(agent_id))

    def agent_finish(
        self, agent_id: str, output_snippet: str | None = None, duration_ms: int | None = None
    ) -> None:
        payload: dict[str, Any] = {}
        if output_snippet is not None:
            payload["output_snippet"] = output_snippet
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        self.emit("agent_finish", payload, from_ref=agent_ref(agent_id))

    # -- model calls -------------------------------------------------------
    def llm_call(
        self,
        agent_id: str,
        provider: str,
        model_name: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        cost_usd: float | None = None,
        prompt_snippet: str | None = None,
        response_snippet: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"provider": provider, "model": model_name}
        for key, value in (
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
            ("latency_ms", latency_ms),
            ("cost_usd", cost_usd),
            ("prompt_snippet", prompt_snippet),
            ("response_snippet", response_snippet),
        ):
            if value is not None:
                payload[key] = value
        self.emit(
            "llm_call",
            payload,
            from_ref=agent_ref(agent_id),
            to_ref=model_ref(provider, model_name),
        )

    # -- tools -------------------------------------------------------------
    def tool_call(
        self,
        agent_id: str,
        tool_id: str,
        name: str | None = None,
        input_snippet: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"name": name or tool_id}
        if input_snippet is not None:
            payload["input_snippet"] = input_snippet
        self.emit("tool_call", payload, from_ref=agent_ref(agent_id), to_ref=tool_ref(tool_id))

    def tool_result(
        self,
        tool_id: str,
        agent_id: str,
        ok: bool = True,
        latency_ms: int | None = None,
        output_snippet: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"ok": ok}
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if output_snippet is not None:
            payload["output_snippet"] = output_snippet
        self.emit("tool_result", payload, from_ref=tool_ref(tool_id), to_ref=agent_ref(agent_id))

    # -- agent-to-agent ----------------------------------------------------
    def handoff(
        self,
        from_agent: str,
        to_agent: str,
        reason: str | None = None,
        context_snippet: str | None = None,
    ) -> None:
        """Control passes from one agent to another — the event necto exists for."""
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        if context_snippet is not None:
            payload["context_snippet"] = context_snippet
        self.emit(
            "handoff", payload, from_ref=agent_ref(from_agent), to_ref=agent_ref(to_agent)
        )

    def message(
        self,
        from_agent: str,
        to_agent: str,
        content_snippet: str,
        intent: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"content_snippet": content_snippet}
        if intent is not None:
            payload["intent"] = intent
        self.emit(
            "message", payload, from_ref=agent_ref(from_agent), to_ref=agent_ref(to_agent)
        )

    # -- state / errors ----------------------------------------------------
    def state_write(self, agent_id: str, key: str, value_snippet: str | None = None) -> None:
        payload: dict[str, Any] = {"key": key}
        if value_snippet is not None:
            payload["value_snippet"] = value_snippet
        self.emit("state_write", payload, from_ref=agent_ref(agent_id), to_ref="state:memory")

    def error(
        self,
        source_id: str,
        message: str,
        stack: str | None = None,
        recoverable: bool | None = None,
    ) -> None:
        """Record an error. `source_id` may be a bare id ('writer') or a full ref
        ('tool:web_search')."""
        payload: dict[str, Any] = {"message": message}
        if stack is not None:
            payload["stack"] = stack
        if recoverable is not None:
            payload["recoverable"] = recoverable
        from_ref = source_id if ":" in source_id else agent_ref(source_id)
        self.emit("error", payload, from_ref=from_ref)


class Necto:
    """The tracer. Create one per application and share it."""

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        api_key: str | None = None,
        transport: Transport | None = None,
        enabled: bool = True,
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
        background: bool = True,
        framework: str | None = None,
    ) -> None:
        self.enabled = enabled
        self.framework = framework
        self._batch_size = max(1, int(batch_size))
        self._flush_interval = max(0.05, float(flush_interval))

        if transport is not None:
            self._transport: Transport = transport
        elif enabled and endpoint:
            self._transport = HttpTransport(endpoint, api_key)
        else:
            self._transport = NullTransport()

        self._lock = threading.Lock()
        self._buffer: list[tuple[str, dict[str, Any]]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if enabled and background:
            self._thread = threading.Thread(
                target=self._loop, name="necto-flush", daemon=True
            )
            self._thread.start()

    # -- plumbing ----------------------------------------------------------
    def _safe(self, fn, *args: Any) -> Any:
        """Call a transport method, swallowing anything it throws."""
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001 - the SDK must never break the host app
            logger.warning("necto: transport call %r failed", getattr(fn, "__name__", fn))
            return None

    def _append(self, run_id: str, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._buffer.append((run_id, event))
            should_flush = len(self._buffer) >= self._batch_size
        if should_flush:
            self.flush()

    def _loop(self) -> None:
        while not self._stop.wait(self._flush_interval):
            try:
                self.flush()
            except Exception:  # noqa: BLE001
                logger.warning("necto: background flush failed")

    def flush(self) -> None:
        """Ship everything currently buffered. Safe to call from any thread."""
        with self._lock:
            if not self._buffer:
                return
            batch, self._buffer = self._buffer, []

        grouped: dict[str, list[dict[str, Any]]] = {}
        for run_id, event in batch:
            grouped.setdefault(run_id, []).append(event)
        for run_id, events in grouped.items():
            self._safe(self._transport.append_events, run_id, events)

    # -- public API --------------------------------------------------------
    def _run_meta(self, meta: dict[str, Any] | None) -> dict[str, Any]:
        run_meta = dict(meta or {})
        if self.framework:
            run_meta.setdefault("framework", self.framework)
        run_meta.setdefault("sdk_version", __import__("necto_sdk").__version__)
        return run_meta

    def start_run(
        self, name: str | None = None, meta: dict[str, Any] | None = None
    ) -> Run:
        """Create a run and return its handle. Pair with `run.finish()`.

        Use this from integrations that cannot use the `with` form.
        """
        run_id = None
        if self.enabled:
            run_id = self._safe(self._transport.create_run, name, self._run_meta(meta))
        return Run(self, run_id if isinstance(run_id, str) else None)

    @contextmanager
    def run(self, name: str | None = None, meta: dict[str, Any] | None = None) -> Iterator[Run]:
        """Start a run, yield a Run handle, and finish it on exit."""
        run = self.start_run(name, meta)
        try:
            yield run
        finally:
            run.finish()

    def close(self) -> None:
        """Stop the background thread and flush remaining events."""
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.flush()

    def __enter__(self) -> Necto:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
