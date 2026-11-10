"""OpenAI Agents SDK integration.

The OpenAI Agents SDK ships its own tracing layer: a `TracingProcessor` receives
trace and span lifecycle events. Registering one is the supported way to observe
runs, so this adapter implements that interface.

Usage (two lines):

    from necto_sdk import Necto
    from necto_sdk.adapters.openai_agents import instrument

    necto = Necto(endpoint="http://127.0.0.1:8000", framework="openai-agents")
    instrument(necto)

    result = await Runner.run(agent, "hello")

Mapping:

| span type        | necto event                        |
|------------------|------------------------------------|
| trace start/end  | create / finish the run            |
| `agent`          | `agent_start` / `agent_finish`      |
| `handoff`        | `handoff`                          |
| `generation`     | `llm_call` (model, tokens, latency) |
| `function`       | `tool_call` / `tool_result`         |

This module never imports `agents` at module load — the processor is duck-typed,
so importing it without the SDK installed is safe. Only `instrument()` requires
the SDK, and it raises a clear ImportError if it is missing.
"""

from __future__ import annotations

import functools
import logging
from datetime import datetime
from typing import Any

from ..tracer import Necto, Run

logger = logging.getLogger(__name__)


def _guard(method):
    """Processors must never raise into the agents runtime."""

    @functools.wraps(method)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return method(self, *args, **kwargs)
        except Exception:  # noqa: BLE001 - never break the user's agent run
            logger.warning(
                "necto: openai-agents adapter failed in %s", method.__name__, exc_info=True
            )
            return None

    return wrapper


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def _latency_ms(start: Any, end: Any) -> int | None:
    if isinstance(start, datetime) and isinstance(end, datetime):
        return int((end - start).total_seconds() * 1000)
    return None


def _tokens(usage: Any) -> tuple[int | None, int | None]:
    if not isinstance(usage, dict):
        return None, None
    return (
        usage.get("input_tokens") or usage.get("prompt_tokens"),
        usage.get("output_tokens") or usage.get("completion_tokens"),
    )


def _provider(model: str | None) -> str:
    lowered = (model or "").lower()
    if "claude" in lowered or "anthropic" in lowered:
        return "anthropic"
    if "gemini" in lowered:
        return "google"
    return "openai"


class NectoProcessor:
    """A `TracingProcessor` that forwards OpenAI Agents activity to necto."""

    def __init__(
        self,
        necto: Necto,
        *,
        name: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.necto = necto
        self.name = name
        self.meta = dict(meta or {})
        self._run: Run | None = None
        self._agents: list[str] = []
        self._tools: dict[Any, str] = {}

    @property
    def run(self) -> Run | None:
        return self._run

    def _ensure_run(self, name: str | None = None) -> Run:
        if self._run is None:
            self._run = self.necto.start_run(name or self.name, self.meta)
        return self._run

    def _current_agent(self) -> str:
        return self._agents[-1] if self._agents else "unknown"

    @staticmethod
    def _key(span: Any) -> Any:
        return _attr(span, "span_id", "id", default=id(span))

    # -- trace lifecycle ---------------------------------------------------
    @_guard
    def on_trace_start(self, trace: Any) -> None:
        name = _attr(trace, "workflow_name", "name") or self.name
        self._ensure_run(str(name) if name else None)

    @_guard
    def on_trace_end(self, trace: Any) -> None:
        if self._run is not None:
            self._run.finish()
            self._run = None

    @_guard
    def shutdown(self) -> None:
        if self._run is not None:
            self._run.finish()
            self._run = None

    @_guard
    def force_flush(self) -> None:
        self.necto.flush()

    # -- spans -------------------------------------------------------------
    @_guard
    def on_span_start(self, span: Any) -> None:
        data = getattr(span, "span_data", None)
        kind = getattr(data, "type", None)
        run = self._ensure_run()

        if kind == "agent":
            agent = str(_attr(data, "name", default="agent"))
            self._agents.append(agent)
            run.agent_start(agent, name=agent)
        elif kind == "function":
            name = str(_attr(data, "name", default="tool"))
            self._tools[self._key(span)] = name
            run.tool_call(self._current_agent(), name, name=name)

    @_guard
    def on_span_end(self, span: Any) -> None:
        data = getattr(span, "span_data", None)
        kind = getattr(data, "type", None)
        run = self._ensure_run()
        latency = _latency_ms(_attr(span, "started_at"), _attr(span, "ended_at"))

        if kind == "agent":
            agent = str(_attr(data, "name", default="agent"))
            run.agent_finish(agent, duration_ms=latency)
            if self._agents and self._agents[-1] == agent:
                self._agents.pop()
        elif kind == "handoff":
            from_agent = str(_attr(data, "from_agent", default="unknown"))
            to_agent = str(_attr(data, "to_agent", default="unknown"))
            run.handoff(from_agent, to_agent, reason="openai_agents_handoff")
        elif kind == "generation":
            model = str(_attr(data, "model", default="unknown"))
            input_tokens, output_tokens = _tokens(_attr(data, "usage"))
            run.llm_call(
                self._current_agent(),
                _provider(model),
                model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency,
            )
        elif kind == "function":
            name = self._tools.pop(self._key(span), None)
            if name is None:
                name = str(_attr(data, "name", default="tool"))
            output = _attr(data, "output")
            run.tool_result(
                name,
                self._current_agent(),
                ok=True,
                latency_ms=latency,
                output_snippet=str(output) if output is not None else None,
            )


def instrument(
    necto: Necto, *, name: str | None = None, meta: dict[str, Any] | None = None
) -> NectoProcessor:
    """Register a necto processor with the OpenAI Agents SDK.

    Raises ImportError when `openai-agents` is not installed.
    """
    try:
        from agents.tracing import add_trace_processor  # noqa: PLC0415 - optional dependency
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "The openai-agents package is required for this adapter: pip install openai-agents"
        ) from exc

    processor = NectoProcessor(necto, name=name, meta=meta)
    add_trace_processor(processor)
    return processor
