# Examples

Runnable ways to get data into necto — from "no dependencies" to real model providers.

| Example | Needs | Shows |
|---|---|---|
| [`plain_sdk.py`](plain_sdk.py) | nothing | the tracer API: agents, an llm_call, a handoff, a tool round-trip |
| [`langgraph_app.py`](langgraph_app.py) | `pip install langgraph langchain-openai` + `OPENAI_API_KEY` | real LangGraph app with real token usage, mapped automatically |
| [`openai_agents_app.py`](openai_agents_app.py) | `pip install openai-agents` + `OPENAI_API_KEY` | OpenAI Agents SDK with a real handoff between two agents |

Start the server first (`cd server && uv run uvicorn necto_server.main:app --reload`) and the UI
(`cd web && pnpm dev`), then:

```bash
python examples/plain_sdk.py
```

Each script prints the run id and a ready-to-open UI link.

## Adding your own agents and models

Every agent is just a ref: `agent:<id>`. Models are provider-namespaced: `model:<provider>:<name>`.

```python
with necto.run(name="my-pipeline") as run:
    run.agent_start("planner", name="Planner")                       # node: agent:planner
    run.llm_call("planner", "openai", "gpt-4o-mini",                 # edge: agent:planner → model:openai:gpt-4o-mini
                 input_tokens=812, output_tokens=95,
                 cost_usd=0.0021, latency_ms=640)
    run.tool_call("planner", "web_search")                           # node: tool:web_search
    run.tool_result("web_search", "planner", ok=True, latency_ms=430)
    run.handoff("planner", "writer", reason="draft ready")           # the highlighted edge
```

The adapters do this for you when a framework is available; the plain tracer is the escape hatch
for anything else (or post raw events to `POST /v1/runs/{id}/events` from any language).

**Tip:** token counts and costs are whatever you report — pass them from the provider response so
the stats dashboard is accurate. LangChain/OpenAI adapters read them automatically.
