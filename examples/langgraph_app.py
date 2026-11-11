#!/usr/bin/env python3
"""Instrument a real LangGraph app — real LLM calls, real token usage.

Setup:
    pip install langgraph langchain-openai
    export OPENAI_API_KEY=sk-...        # PowerShell: $env:OPENAI_API_KEY = "sk-..."

    python examples/langgraph_app.py

Open the printed URL to see the graph. The necto adapter maps LangGraph nodes to agents,
node-to-node transitions to handoffs, and chat calls to llm_call (with tokens + latency).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk"))

from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

from necto_sdk import Necto  # noqa: E402
from necto_sdk.adapters.langgraph import NectoCallbackHandler  # noqa: E402


class State(TypedDict):
    topic: str
    research: str
    draft: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--ui", default="http://localhost:5173")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--topic", default="event-driven architecture")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    necto = Necto(endpoint=args.endpoint, api_key=args.api_key, framework="langgraph")
    handler = NectoCallbackHandler(necto, name="blog-graph")
    llm = ChatOpenAI(model=args.model, temperature=0)

    def research(state: State) -> State:
        message = llm.invoke(f"List three key facts about {state['topic']}.")
        return {"research": str(message.content)}

    def write(state: State) -> State:
        message = llm.invoke(
            f"Write a two-sentence intro about {state['topic']} using: {state['research']}"
        )
        return {"draft": str(message.content)}

    graph = StateGraph(State)
    graph.add_node("researcher", research)
    graph.add_node("writer", write)
    graph.add_edge(START, "researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", END)
    app = graph.compile()

    result = app.invoke({"topic": args.topic}, config={"callbacks": [handler]})
    necto.close()

    print("draft:", result["draft"][:200])
    print("run:", handler.last_run_id)
    print("open:", f"{args.ui}/?run={handler.last_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
