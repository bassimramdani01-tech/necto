"""Real LangGraph integration.

Skipped unless the optional framework extra is installed:

    cd sdk && uv sync --group frameworks

These tests run an actual LangGraph StateGraph with a fake chat model, so the adapter is
exercised against the real callback machinery rather than hand-built mocks.
"""

import pytest

pytest.importorskip("langgraph")

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402

from necto_sdk import Necto, RecordingTransport  # noqa: E402
from necto_sdk.adapters.langgraph import NectoCallbackHandler  # noqa: E402


class State(TypedDict, total=False):
    research: str
    draft: str


def _graph() -> StateGraph:
    model = GenericFakeChatModel(
        messages=iter([AIMessage(content="three facts"), AIMessage(content="a draft")])
    )

    def research(state: State) -> State:
        return {"research": str(model.invoke("research").content)}

    def write(state: State) -> State:
        return {"draft": str(model.invoke("write").content)}

    graph = StateGraph(State)
    graph.add_node("researcher", research)
    graph.add_node("writer", write)
    graph.add_edge(START, "researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", END)
    return graph


def test_real_langgraph_run_emits_agents_handoffs_and_llm_calls():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=False)
    handler = NectoCallbackHandler(necto, name="integration-graph")

    app = _graph().compile()
    result = app.invoke({}, config={"callbacks": [handler]})
    necto.close()

    assert result["draft"] == "a draft"

    events = transport.all_events()
    types = [event["type"] for event in events]
    assert "agent_start" in types
    assert "handoff" in types
    assert "llm_call" in types

    agents = {event["to"] for event in events if event["type"] == "agent_start"}
    assert {"agent:researcher", "agent:writer"} <= agents

    handoffs = [event for event in events if event["type"] == "handoff"]
    assert handoffs[0]["from"] == "agent:researcher"
    assert handoffs[0]["to"] == "agent:writer"

    assert handler.last_run_id == transport.runs[0]["id"]
