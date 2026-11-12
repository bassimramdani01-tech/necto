import pytest

from necto_sdk import Necto, RecordingTransport
from necto_sdk.adapters.otel import NectoSpanProcessor, instrument

try:  # opentelemetry may or may not be installed in the test environment
    import opentelemetry  # noqa: F401

    OTEL_INSTALLED = True
except ImportError:  # pragma: no cover
    OTEL_INSTALLED = False


class Status:
    def __init__(self, name="UNSET"):
        self.status_code = name


class Context:
    def __init__(self, span_id):
        self.span_id = span_id


class Span:
    def __init__(self, name, attributes=None, span_id=None, start=0, end=0, parent="root"):
        self.name = name
        self.attributes = attributes or {}
        self.context = Context(span_id or id(self))
        self.start_time = start
        self.end_time = end
        self.parent = parent
        self.status = Status()


def setup():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=False)
    return transport, NectoSpanProcessor(necto, name="otel-run")


def collected(transport, processor):
    """Tool results/blocks are buffered; flush before asserting."""
    processor.force_flush()
    return transport.all_events()


def test_agent_span_becomes_agent_events():
    transport, p = setup()
    span = Span(
        "invoke_agent triage",
        {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "triage"},
    )
    p.on_start(span)
    p.on_end(span)

    events = collected(transport, p)
    assert [e["type"] for e in events] == ["agent_start", "agent_finish"]
    assert events[0]["to"] == "agent:triage"


def test_chat_span_becomes_llm_call_with_tokens_and_latency():
    transport, p = setup()
    span = Span(
        "chat gpt-4o-mini",
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4o-mini",
            "gen_ai.usage.input_tokens": 100,
            "gen_ai.usage.output_tokens": 25,
        },
        start=1_000_000_000,
        end=1_640_000_000,
    )
    p.on_end(span)

    call = collected(transport, p)[0]
    assert call["type"] == "llm_call"
    assert call["to"] == "model:openai:gpt-4o-mini"
    assert call["payload"]["input_tokens"] == 100
    assert call["payload"]["output_tokens"] == 25
    assert call["payload"]["latency_ms"] == 640


def test_tool_span_becomes_call_and_result():
    transport, p = setup()
    span = Span(
        "execute_tool web_search",
        {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "web_search"},
    )
    p.on_start(span)
    p.on_end(span)

    events = collected(transport, p)
    call = next(e for e in events if e["type"] == "tool_call")
    result = next(e for e in events if e["type"] == "tool_result")
    assert call["to"] == "tool:web_search"
    assert result["payload"]["ok"] is True


def test_agent_transition_emits_handoff():
    transport, p = setup()
    p.on_start(
        Span(
            "invoke_agent triage",
            {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "triage"},
            span_id=1,
        )
    )
    second = Span(
        "invoke_agent booking",
        {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "booking"},
        span_id=2,
    )
    p.on_start(second)
    p.on_end(second)

    handoffs = [e for e in collected(transport, p) if e["type"] == "handoff"]
    assert len(handoffs) == 1
    assert handoffs[0]["from"] == "agent:triage"
    assert handoffs[0]["to"] == "agent:booking"


def test_explicit_necto_attributes_emit_handoff():
    transport, p = setup()
    p.on_end(Span("custom", {"necto.from": "agent:a", "necto.to": "agent:b"}))

    handoffs = [e for e in collected(transport, p) if e["type"] == "handoff"]
    assert handoffs[0]["from"] == "agent:a"
    assert handoffs[0]["to"] == "agent:b"


def test_root_span_end_finishes_run():
    transport, p = setup()
    p.on_end(Span("chat gpt-4o-mini", {"gen_ai.operation.name": "chat"}, parent=None))
    assert transport.runs
    assert transport.finished[0]["status"] == "ok"


def test_error_status_marks_tool_result_not_ok():
    transport, p = setup()
    span = Span("execute_tool web_search", {"gen_ai.operation.name": "execute_tool"})
    span.status = Status("ERROR")
    p.on_start(span)
    p.on_end(span)

    result = next(e for e in collected(transport, p) if e["type"] == "tool_result")
    assert result["payload"]["ok"] is False


def test_processor_swallows_exceptions():
    _, p = setup()

    class Boom:
        def tool_call(self, *a, **k):
            raise RuntimeError("necto broke")

    p._run = Boom()
    p.on_start(Span("execute_tool x", {"gen_ai.operation.name": "execute_tool"}))


def test_anthropic_provider_inferred_from_model():
    transport, p = setup()
    p.on_end(
        Span("chat", {"gen_ai.operation.name": "chat", "gen_ai.request.model": "claude-sonnet-4"})
    )
    call = collected(transport, p)[0]
    assert call["to"] == "model:anthropic:claude-sonnet-4"


def test_instrument_registers_on_given_provider():
    class FakeProvider:
        def __init__(self):
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    provider = FakeProvider()
    processor = instrument(Necto(background=False), tracer_provider=provider)
    assert provider.processors == [processor]


@pytest.mark.skipif(not OTEL_INSTALLED, reason="opentelemetry not installed")
def test_instrument_without_sdk_provider_raises_clear_error():
    with pytest.raises(RuntimeError, match="TracerProvider"):
        instrument(Necto(background=False))


@pytest.mark.skipif(OTEL_INSTALLED, reason="opentelemetry is installed")
def test_instrument_without_otel_raises_import_error():
    with pytest.raises(ImportError, match="opentelemetry"):
        instrument(Necto(background=False))
