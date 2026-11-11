from datetime import datetime, timedelta

import pytest

from necto_sdk import Necto, RecordingTransport
from necto_sdk.adapters.openai_agents import NectoProcessor, instrument


class Data:
    def __init__(self, type_, **kwargs):
        self.type = type_
        for key, value in kwargs.items():
            setattr(self, key, value)


class Span:
    def __init__(self, span_id, data, started=None, ended=None):
        self.span_id = span_id
        self.span_data = data
        self.started_at = started
        self.ended_at = ended


class Trace:
    def __init__(self, workflow_name="Support workflow"):
        self.workflow_name = workflow_name


def setup():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=False)
    return transport, NectoProcessor(necto)


def agent_span(span_id, name):
    return Span(span_id, Data("agent", name=name))


def test_trace_lifecycle_creates_and_finishes_run():
    transport, p = setup()
    p.on_trace_start(Trace("Support workflow"))
    assert transport.runs[0]["name"] == "Support workflow"
    assert p.last_run_id == transport.runs[0]["id"]
    p.on_trace_end(Trace())
    assert transport.finished[0]["status"] == "ok"


def test_agent_spans_become_agents():
    transport, p = setup()
    p.on_trace_start(Trace())
    p.on_span_start(agent_span("a1", "triage"))
    p.on_span_end(agent_span("a1", "triage"))
    p.on_trace_end(Trace())

    events = transport.all_events()
    starts = [e for e in events if e["type"] == "agent_start"]
    finishes = [e for e in events if e["type"] == "agent_finish"]
    assert starts[0]["to"] == "agent:triage"
    assert finishes[0]["from"] == "agent:triage"


def test_handoff_span_emits_handoff():
    transport, p = setup()
    p.on_trace_start(Trace())
    p.on_span_end(
        Span("h1", Data("handoff", from_agent="triage", to_agent="refunds"))
    )
    p.on_trace_end(Trace())

    handoffs = [e for e in transport.all_events() if e["type"] == "handoff"]
    assert len(handoffs) == 1
    assert handoffs[0]["from"] == "agent:triage"
    assert handoffs[0]["to"] == "agent:refunds"


def test_generation_span_becomes_llm_call_with_tokens():
    transport, p = setup()
    start = datetime(2025, 1, 1, 10, 0, 0)
    p.on_trace_start(Trace())
    p.on_span_start(agent_span("a1", "triage"))
    p.on_span_end(
        Span(
            "g1",
            Data(
                "generation",
                model="gpt-4o-mini",
                usage={"input_tokens": 120, "output_tokens": 48},
            ),
            started=start,
            ended=start + timedelta(milliseconds=640),
        )
    )
    p.on_trace_end(Trace())

    calls = [e for e in transport.all_events() if e["type"] == "llm_call"]
    assert len(calls) == 1
    call = calls[0]
    assert call["from"] == "agent:triage"
    assert call["to"] == "model:openai:gpt-4o-mini"
    assert call["payload"]["input_tokens"] == 120
    assert call["payload"]["output_tokens"] == 48
    assert call["payload"]["latency_ms"] == 640


def test_anthropic_model_gets_correct_provider():
    transport, p = setup()
    p.on_trace_start(Trace())
    p.on_span_end(Span("g1", Data("generation", model="claude-sonnet-4")))
    p.on_trace_end(Trace())

    call = next(e for e in transport.all_events() if e["type"] == "llm_call")
    assert call["to"] == "model:anthropic:claude-sonnet-4"


def test_function_span_becomes_tool_call_and_result():
    transport, p = setup()
    p.on_trace_start(Trace())
    p.on_span_start(agent_span("a1", "researcher"))
    p.on_span_start(Span("f1", Data("function", name="web_search")))
    p.on_span_end(Span("f1", Data("function", name="web_search", output="3 results")))
    p.on_trace_end(Trace())

    events = transport.all_events()
    call = next(e for e in events if e["type"] == "tool_call")
    result = next(e for e in events if e["type"] == "tool_result")
    assert call["from"] == "agent:researcher"
    assert call["to"] == "tool:web_search"
    assert result["from"] == "tool:web_search"
    assert result["to"] == "agent:researcher"


def test_processor_swallows_exceptions():
    transport, p = setup()

    class Boom:
        def agent_start(self, *a, **k):
            raise RuntimeError("necto broke")

    p._run = Boom()
    p.on_span_start(agent_span("a1", "triage"))  # must not raise


def test_instrument_without_sdk_raises_clear_error():
    necto = Necto(background=False)
    with pytest.raises(ImportError, match="openai-agents"):
        instrument(necto)
