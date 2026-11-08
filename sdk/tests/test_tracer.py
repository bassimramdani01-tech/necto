import pytest

from necto_sdk import Necto, RecordingTransport


def make_tracer():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=False)
    return necto, transport


def test_run_creates_run_and_flushes_events():
    necto, transport = make_tracer()
    with necto.run(name="demo") as run:
        run.agent_start("router", name="Router", framework="langgraph")
        run.handoff("router", "researcher", reason="needs sources")

    necto.flush()

    assert len(transport.runs) == 1
    assert transport.runs[0]["name"] == "demo"
    events = transport.all_events()
    assert [e["type"] for e in events] == ["agent_start", "handoff"]
    assert events[1]["from"] == "agent:router"
    assert events[1]["to"] == "agent:researcher"
    assert transport.finished[0]["status"] == "ok"


def test_meta_includes_sdk_version_and_framework():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=False, framework="langgraph")
    with necto.run(name="r"):
        pass
    meta = transport.runs[0]["meta"]
    assert meta["framework"] == "langgraph"
    assert "sdk_version" in meta


def test_llm_call_builds_model_ref():
    necto, transport = make_tracer()
    with necto.run() as run:
        run.llm_call("router", "openai", "gpt-4o-mini", input_tokens=10, output_tokens=5, cost_usd=0.001)
    necto.flush()

    event = transport.all_events()[0]
    assert event["type"] == "llm_call"
    assert event["from"] == "agent:router"
    assert event["to"] == "model:openai:gpt-4o-mini"
    assert event["payload"]["input_tokens"] == 10


def test_tool_call_and_result_refs():
    necto, transport = make_tracer()
    with necto.run() as run:
        run.tool_call("researcher", "web_search", name="web_search")
        run.tool_result("web_search", "researcher", ok=True, latency_ms=120)
    necto.flush()

    call, result = transport.all_events()
    assert (call["from"], call["to"]) == ("agent:researcher", "tool:web_search")
    assert (result["from"], result["to"]) == ("tool:web_search", "agent:researcher")


def test_batch_size_triggers_early_flush():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=False, batch_size=2)
    with necto.run() as run:
        run.handoff("a", "b")
        assert transport.all_events() == []  # nothing yet
        run.handoff("b", "c")
    assert len(transport.all_events()) == 2  # flushed at threshold


def test_disabled_tracer_is_a_noop():
    transport = RecordingTransport()
    necto = Necto(transport=transport, enabled=False, background=False)
    with necto.run() as run:
        assert run.disabled
        run.handoff("a", "b")
    assert transport.runs == []
    assert transport.all_events() == []


def test_no_endpoint_means_disabled():
    necto = Necto(background=False)
    with necto.run() as run:
        assert run.disabled


def test_transport_errors_never_raise():
    class Broken:
        def create_run(self, name, meta):
            raise RuntimeError("boom")

        def append_events(self, run_id, events):
            raise RuntimeError("boom")

        def finish_run(self, run_id, status, output):
            raise RuntimeError("boom")

    necto = Necto(transport=Broken(), background=False)
    with necto.run() as run:
        run.handoff("a", "b")  # must not raise
    necto.flush()  # must not raise


def test_explicit_finish_is_idempotent():
    necto, transport = make_tracer()
    with necto.run() as run:
        run.finish(status="ok")
        run.finish(status="error")  # ignored
    assert len(transport.finished) == 1
    assert transport.finished[0]["status"] == "ok"


def test_background_flush_delivers_events():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=True, flush_interval=0.05)
    try:
        with necto.run() as run:
            run.handoff("a", "b")
        necto.close()
    finally:
        necto.close()
    assert len(transport.all_events()) >= 1

def test_error_accepts_bare_id_or_full_ref():
    necto, transport = make_tracer()
    with necto.run() as run:
        run.error("writer", "boom")
        run.error("tool:web_search", "tool failed")
    necto.flush()

    first, second = transport.all_events()
    assert first["from"] == "agent:writer"
    assert second["from"] == "tool:web_search"
