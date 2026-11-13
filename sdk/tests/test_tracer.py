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
        run.llm_call(
            "router", "openai", "gpt-4o-mini", input_tokens=10, output_tokens=5, cost_usd=0.001
        )
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


def test_state_write_uses_state_ref():
    necto, transport = make_tracer()
    with necto.run() as run:
        run.state_write("planner", "plan", "step 1", state_id="scratch")
    necto.flush()

    event = transport.all_events()[0]
    assert event["type"] == "state_write"
    assert event["from"] == "agent:planner"
    assert event["to"] == "state:scratch"


def test_state_write_defaults_to_memory_state():
    necto, transport = make_tracer()
    with necto.run() as run:
        run.state_write("planner", "plan")
    necto.flush()
    assert transport.all_events()[0]["to"] == "state:memory"


def test_no_background_thread_when_nothing_can_deliver():
    necto = Necto()  # no endpoint, no transport -> nothing to flush
    try:
        assert necto._thread is None
    finally:
        necto.close()


def test_from_env_reads_endpoint_key_and_framework(monkeypatch):
    monkeypatch.setenv("NECTO_ENDPOINT", "http://localhost:9999")
    monkeypatch.setenv("NECTO_API_KEY", "secret")
    monkeypatch.setenv("NECTO_FRAMEWORK", "langgraph")

    necto = Necto.from_env()
    necto.close()

    assert necto.framework == "langgraph"
    assert necto._transport.endpoint == "http://localhost:9999"
    assert necto._transport.api_key == "secret"


def test_from_env_can_be_disabled(monkeypatch):
    from necto_sdk import NullTransport

    monkeypatch.setenv("NECTO_ENDPOINT", "http://localhost:9999")
    monkeypatch.setenv("NECTO_ENABLED", "off")

    necto = Necto.from_env()
    necto.close()

    assert necto.enabled is False
    assert isinstance(necto._transport, NullTransport)


def test_from_env_kwargs_override_environment(monkeypatch):
    monkeypatch.setenv("NECTO_FRAMEWORK", "langgraph")

    transport = RecordingTransport()
    necto = Necto.from_env(transport=transport, framework="custom")
    necto.close()

    assert necto.framework == "custom"
    assert necto._transport is transport


def test_atexit_flushes_on_exit(monkeypatch):
    import necto_sdk.tracer as tracer_module

    registered = []
    monkeypatch.setattr(
        tracer_module.atexit, "register", lambda fn, *args, **kwargs: registered.append(fn)
    )

    necto, transport = make_tracer()
    with necto.run(name="atexit-demo") as run:
        run.handoff("a", "b")

    # Simulate interpreter exit running the registered callback (no explicit close()).
    for callback in registered:
        callback()

    assert [event["type"] for event in transport.all_events()] == ["handoff"]


def test_close_is_idempotent(monkeypatch):
    necto, transport = make_tracer()
    with necto.run(name="close-twice") as run:
        run.handoff("a", "b")

    necto.close()
    necto.close()

    assert len(transport.all_events()) == 1
    assert len(transport.runs) == 1
