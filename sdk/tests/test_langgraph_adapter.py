import pytest

from necto_sdk import Necto, RecordingTransport
from necto_sdk.adapters.langgraph import NectoCallbackHandler, attach


class FakeResponse:
    def __init__(self, prompt_tokens=None, completion_tokens=None):
        self.llm_output = (
            {
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            }
            if prompt_tokens is not None
            else {}
        )
        self.generations = []


def setup():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=False)
    handler = NectoCallbackHandler(necto, name="graph")
    return transport, handler


def node_start(handler, run_id, parent_id, node):
    handler.on_chain_start(
        {"name": node}, {}, run_id=run_id, parent_run_id=parent_id,
        metadata={"langgraph_node": node},
    )


def test_root_chain_creates_and_finishes_run():
    transport, handler = setup()
    handler.on_chain_start({"name": "graph"}, {"q": "hi"}, run_id="root")
    assert len(transport.runs) == 1
    assert transport.runs[0]["name"] == "graph"
    handler.on_chain_end({}, run_id="root")
    assert transport.finished[0]["status"] == "ok"


def test_node_transition_emits_handoff():
    transport, handler = setup()
    handler.on_chain_start({"name": "graph"}, {}, run_id="root")
    node_start(handler, "n1", "root", "router")
    handler.on_chain_end({}, run_id="n1", parent_run_id="root")
    node_start(handler, "n2", "root", "researcher")
    handler.on_chain_end({}, run_id="root")

    events = transport.all_events()
    handoffs = [e for e in events if e["type"] == "handoff"]
    assert len(handoffs) == 1
    assert handoffs[0]["from"] == "agent:router"
    assert handoffs[0]["to"] == "agent:researcher"

    starts = [e for e in events if e["type"] == "agent_start"]
    assert {e["to"] for e in starts} == {"agent:router", "agent:researcher"}


def test_same_node_twice_does_not_emit_handoff():
    transport, handler = setup()
    handler.on_chain_start({"name": "graph"}, {}, run_id="root")
    node_start(handler, "n1", "root", "router")
    node_start(handler, "n2", "root", "router")
    handler.on_chain_end({}, run_id="root")

    handoffs = [e for e in transport.all_events() if e["type"] == "handoff"]
    assert handoffs == []


def test_llm_end_records_tokens_latency_and_model():
    transport, handler = setup()
    handler.on_chain_start({"name": "graph"}, {}, run_id="root")
    node_start(handler, "n1", "root", "router")
    handler.on_chat_model_start(
        {"name": "ChatOpenAI", "model_name": "gpt-4o-mini"}, [[]],
        run_id="l1", parent_run_id="n1",
    )
    handler.on_llm_end(FakeResponse(10, 5), run_id="l1", parent_run_id="n1")
    handler.on_chain_end({}, run_id="root")

    calls = [e for e in transport.all_events() if e["type"] == "llm_call"]
    assert len(calls) == 1
    call = calls[0]
    assert call["from"] == "agent:router"
    assert call["to"] == "model:openai:gpt-4o-mini"
    assert call["payload"]["input_tokens"] == 10
    assert call["payload"]["output_tokens"] == 5
    assert call["payload"]["latency_ms"] >= 0


def test_tool_call_and_result():
    transport, handler = setup()
    handler.on_chain_start({"name": "graph"}, {}, run_id="root")
    node_start(handler, "n1", "root", "researcher")
    handler.on_tool_start({"name": "web_search"}, "query", run_id="t1", parent_run_id="n1")
    handler.on_tool_end("3 results", run_id="t1", parent_run_id="n1")
    handler.on_chain_end({}, run_id="root")

    events = transport.all_events()
    call = next(e for e in events if e["type"] == "tool_call")
    result = next(e for e in events if e["type"] == "tool_result")
    assert call["to"] == "tool:web_search"
    assert result["from"] == "tool:web_search"
    assert result["payload"]["ok"] is True


def test_chain_error_emits_error_event():
    transport, handler = setup()
    handler.on_chain_start({"name": "graph"}, {}, run_id="root")
    node_start(handler, "n1", "root", "router")
    handler.on_chain_error(RuntimeError("routing failed"), run_id="n1", parent_run_id="root")
    handler.on_chain_end({}, run_id="root")

    errors = [e for e in transport.all_events() if e["type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["from"] == "agent:router"
    assert "routing failed" in errors[0]["payload"]["message"]


def test_handler_swallows_exceptions_from_necto():
    transport, handler = setup()

    class Boom:
        def handoff(self, *a, **k):
            raise RuntimeError("necto broke")

    handler._run = Boom()
    handler.on_chain_start({"name": "graph"}, {}, run_id="root")
    node_start(handler, "n1", "root", "router")  # must not raise


def test_attach_merges_callbacks():
    handler = NectoCallbackHandler(Necto(background=False))
    config = attach(handler, {"callbacks": ["existing"], "tags": ["x"]})
    assert config["callbacks"] == ["existing", handler]
    assert config["tags"] == ["x"]
