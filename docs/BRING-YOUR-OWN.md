# Bring your own agents and models

necto does not host models or run agents for you — it **records** whatever you build. Three levels,
from "just point it at my stack" to "I want full control".

## Level 1 — describe a pipeline in JSON (new)

[`examples/custom_pipeline.py`](../examples/custom_pipeline.py) executes a config-defined pipeline
with real model calls and records every step.

```bash
# no API keys: keeps the real architecture, fakes only the reply text
python examples/custom_pipeline.py --dry-run

# real calls
OPENAI_API_KEY=sk-...    python examples/custom_pipeline.py             # openai models
ANTHROPIC_API_KEY=sk-... python examples/custom_pipeline.py             # anthropic models
python examples/custom_pipeline.py --config my-pipeline.json --prompt "…"
```

The config (`examples/custom_pipeline.example.json`) is small:

```json
{
  "name": "support-desk",
  "models": {
    "fast":  { "provider": "openai",    "model": "gpt-4o-mini",  "rates": { "input_per_1k": 0.00015, "output_per_1k": 0.0006 } },
    "smart": { "provider": "anthropic", "model": "claude-sonnet-4", "rates": { "input_per_1k": 0.003, "output_per_1k": 0.015 } }
  },
  "tools":  { "lookup_invoice": { "name": "lookup_invoice", "reply": "invoice #5512: duplicate charge" } },
  "agents": [
    { "id": "triage",  "name": "Triage",  "model": "fast",  "system": "Classify the request." },
    { "id": "billing", "name": "Billing", "model": "smart", "system": "Resolve billing issues.", "tools": ["lookup_invoice"] },
    { "id": "writer",  "name": "Reply writer", "model": "fast", "system": "Write a short reply." }
  ],
  "flow": ["triage", "billing", "writer"]
}
```

Each configured agent becomes an `agent` node, each model an `model` node, the flow becomes
`handoff` edges, tools become tool nodes, and token/cost/latency are recorded per call — so the
graph you see *is* the system you defined.

### Providers

| Provider | Env | Notes |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | any OpenAI-compatible `base_url` works (Ollama, vLLM, OpenRouter, Azure) |
| `anthropic` | `ANTHROPIC_API_KEY` | Messages API |
| `mock` | — | deterministic replies for wiring tests |

`rates` are USD per 1k tokens; cost is computed from real usage when the provider returns it.

## Level 2 — your own code with the SDK

Use the plain tracer when you have your own orchestration:

```python
from necto_sdk import Necto

necto = Necto.from_env()  # NECTO_ENDPOINT / NECTO_API_KEY / NECTO_FRAMEWORK
with necto.run(name="my-pipeline") as run:
    run.agent_start("planner", name="Planner")
    run.llm_call(
        "planner", "openai", "gpt-4o-mini", input_tokens=812, output_tokens=95, cost_usd=0.0021
    )
    run.handoff("planner", "writer", reason="draft ready")
    run.tool_call("writer", "publish")
    run.tool_result("publish", "writer", ok=True, latency_ms=90)
```

## Level 3 — frameworks you already use

| Framework | Attach with |
|---|---|
| LangGraph / LangChain | `NectoCallbackHandler(necto)` in `config={"callbacks": [...]}` |
| OpenAI Agents SDK | `instrument(necto)` from `necto_sdk.adapters.openai_agents` |
| OpenTelemetry | `instrument(necto)` from `necto_sdk.adapters.otel` |
| Anything else | `POST /v1/runs` + `POST /v1/runs/{id}/events` (see [SCHEMA.md](SCHEMA.md)) |

## Deploying it

```bash
docker compose up -d --build          # server + UI on http://localhost:8000
# point the SDK at it
NECTO_ENDPOINT=http://localhost:8000 python my_agent.py
```

Set `NECTO_API_KEY` on the server and pass the same key to `Necto(api_key=...)` before exposing it
beyond localhost.
