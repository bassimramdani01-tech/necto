"""OpenTelemetry bridge.

Most agent frameworks either emit OpenTelemetry spans directly or can be made to
with `opentelemetry-instrumentation`. This bridge converts those spans into necto
events, so anything OTel-shaped can feed the graph without a bespoke adapter.

Usage:

    from necto_sdk import Necto
    from necto_sdk.adapters.otel import instrument

    instrument(Necto(endpoint="http://127.0.0.1:8000", framework="otel"))

It understands the OpenTelemetry GenAI semantic conventions:

| attribute / operation                 | necto event                |
|---------------------------------------|----------------------------|
| `gen_ai.operation.name = invoke_agent`| `agent_start` / `agent_finish` |
| `gen_ai.operation.name = chat`        | `llm_call` (model, tokens) |
| `gen_ai.operation.name = execute_tool`| `tool_call` / `tool_result` |
| `necto.from` + `necto.to`             | `handoff`                  |

A change of active agent also emits a handoff (the same heuristic the framework
adapters use). Span status ERROR is recorded as `ok=false` on tool results.

Like the other adapters this module never imports opentelemetry at load time; the
processor is duck-typed. Only `instrument()` requires the SDK.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from ..tracer import Necto, Run

logger = logging.getLogger(__name__)

_AGENT_OPS = frozenset({"invoke_agent", "create_agent"})
_LLM_OPS = frozenset({"chat", "text_completion", "generate_content"})


def _guard(method):
    """Processors must never raise into the telemetry pipeline."""

    @functools.wraps(method)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return method(self, *args, **kwargs)
        except Exception:  # noqa: BLE001 - never break the host application
            logger.warning("necto: otel adapter failed in %s", method.__name__, exc_info=True)
            return None

    return wrapper


def _agent_id(value: Any) -> str:
    """Accept either an agent id ('triage') or a full ref ('agent:triage')."""
    text = str(value)
    return text[len("agent:") :] if text.startswith("agent:") else text


def _attrs(span: Any) -> dict[str, Any]:
    attributes = getattr(span, "attributes", None)
    return dict(attributes) if attributes else {}


def _operation(attrs: dict[str, Any], span: Any) -> str | None:
    op = attrs.get("gen_ai.operation.name")
    if isinstance(op, str) and op:
        return op
    # fall back to well-known span-name prefixes
    name = str(getattr(span, "name", "") or "")
    lowered = name.lower()
    if lowered.startswith(("chat ", "chat", "llm")):
        return "chat"
    if lowered.startswith(("invoke_agent", "agent ")):
        return "invoke_agent"
    if lowered.startswith(("execute_tool", "tool ")):
        return "execute_tool"
    return None


def _provider(attrs: dict[str, Any], model: str) -> str:
    explicit = attrs.get("gen_ai.provider.name") or attrs.get("gen_ai.system")
    if isinstance(explicit, str) and explicit:
        return explicit
    lowered = model.lower()
    if "claude" in lowered or "anthropic" in lowered:
        return "anthropic"
    if "gemini" in lowered:
        return "google"
    return "openai"


def _latency_ms(span: Any) -> int | None:
    start = getattr(span, "start_time", None)
    end = getattr(span, "end_time", None)
    if isinstance(start, int) and isinstance(end, int) and end >= start:
        return int((end - start) / 1_000_000)
    return None


def _is_error(span: Any) -> bool:
    status = getattr(span, "status", None)
    code = getattr(status, "status_code", None)
    name = getattr(code, "name", None) or str(code or "")
    return "ERROR" in str(name).upper()


class NectoSpanProcessor:
    """An OpenTelemetry `SpanProcessor` that forwards GenAI spans to necto."""

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

    def _ensure_run(self) -> Run:
        if self._run is None:
            self._run = self.necto.start_run(self.name, self.meta)
        return self._run

    def _current_agent(self) -> str:
        return self._agents[-1] if self._agents else "unknown"

    @staticmethod
    def _key(span: Any) -> Any:
        context = getattr(span, "context", None)
        span_id = getattr(context, "span_id", None)
        return span_id if span_id is not None else id(span)

    @staticmethod
    def _agent_name(span: Any, attrs: dict[str, Any]) -> str:
        name = attrs.get("gen_ai.agent.name") or attrs.get("gen_ai.agent.id")
        if name:
            return str(name)
        return str(getattr(span, "name", "") or "agent")

    # -- span processor interface -----------------------------------------
    @_guard
    def on_start(self, span: Any, parent_context: Any = None) -> None:
        attrs = _attrs(span)
        op = _operation(attrs, span)
        run = self._ensure_run()

        if op in _AGENT_OPS:
            agent = self._agent_name(span, attrs)
            if self._agents and self._agents[-1] != agent:
                run.handoff(self._agents[-1], agent, reason="otel_agent_transition")
            self._agents.append(agent)
            run.agent_start(agent, name=agent)
        elif op == "execute_tool":
            name = str(attrs.get("gen_ai.tool.name") or getattr(span, "name", "") or "tool")
            self._tools[self._key(span)] = name
            run.tool_call(self._current_agent(), name, name=name)

    @_guard
    def on_end(self, span: Any) -> None:
        attrs = _attrs(span)
        op = _operation(attrs, span)
        run = self._ensure_run()
        latency = _latency_ms(span)
        is_root = getattr(span, "parent", None) is None

        if op in _AGENT_OPS:
            agent = self._agent_name(span, attrs)
            run.agent_finish(agent, duration_ms=latency)
            if self._agents and self._agents[-1] == agent:
                self._agents.pop()
        elif op in _LLM_OPS:
            model = str(
                attrs.get("gen_ai.response.model") or attrs.get("gen_ai.request.model") or "unknown"
            )
            run.llm_call(
                self._current_agent(),
                _provider(attrs, model),
                model,
                input_tokens=attrs.get("gen_ai.usage.input_tokens"),
                output_tokens=attrs.get("gen_ai.usage.output_tokens"),
                latency_ms=latency,
            )
        elif op == "execute_tool":
            name = self._tools.pop(self._key(span), None)
            if name is None:
                name = str(attrs.get("gen_ai.tool.name") or getattr(span, "name", "") or "tool")
            run.tool_result(
                name,
                self._current_agent(),
                ok=not _is_error(span),
                latency_ms=latency,
            )
        elif attrs.get("necto.from") and attrs.get("necto.to"):
            run.handoff(_agent_id(attrs["necto.from"]), _agent_id(attrs["necto.to"]))

        if is_root:
            run.finish(status="error" if _is_error(span) else "ok")
            self._run = None

    @_guard
    def shutdown(self) -> None:
        if self._run is not None:
            self._run.finish()
            self._run = None

    @_guard
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        self.necto.flush()
        return True


def instrument(
    necto: Necto,
    *,
    name: str | None = None,
    meta: dict[str, Any] | None = None,
    tracer_provider: Any = None,
) -> NectoSpanProcessor:
    """Register a necto span processor with OpenTelemetry.

    Raises ImportError when the OpenTelemetry SDK is not installed *and* no
    `tracer_provider` was passed — an explicit provider needs no import.
    """
    provider = tracer_provider
    if provider is None:
        try:
            from opentelemetry import trace  # noqa: PLC0415 - optional dependency
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ImportError(
                "The OpenTelemetry SDK is required for this adapter: pip install opentelemetry-sdk"
            ) from exc
        provider = trace.get_tracer_provider()
    if not hasattr(provider, "add_span_processor"):
        raise RuntimeError(
            "OpenTelemetry is installed but no SDK TracerProvider is configured. "
            "Create one with opentelemetry.sdk.trace.TracerProvider(), register it via "
            "trace.set_tracer_provider(...), or pass it as tracer_provider=..."
        )
    processor = NectoSpanProcessor(necto, name=name, meta=meta)
    provider.add_span_processor(processor)
    return processor
