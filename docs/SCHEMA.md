# necto — Event Schema v1 (normative)

Status: **FROZEN v1.** This is the contract between the SDK, the server, and any third-party emitter.
Changes follow the versioning policy in §2.

---

## 1. Philosophy

1. **Framework-agnostic.** No LangGraph/OpenAI concepts appear here. Adapters translate (§8).
2. **Append-only.** Events are facts about what happened; the server never rewrites them.
3. **One format everywhere.** Wire format = storage format = graph projection input.
4. **Extensible.** Unknown event types and unknown payload fields are stored verbatim, not rejected.

## 2. Versioning policy

- Every event carries `schema_version` (integer). Current version: **1**.
- **Additive change** (new event type, new optional payload field): backward-compatible; servers MUST store unknown types/fields unchanged; no version bump.
- **Breaking change** (rename, remove, or change the meaning of an existing field/type): requires a new major version. Servers reject `schema_version` greater than the supported maximum with HTTP 400 and a clear error message.
- `schema_version` is REQUIRED on every event; missing → HTTP 400.

## 3. The envelope

Every event is one JSON object:

| field | type | required | meaning |
|---|---|---|---|
| `run_id` | string (UUID) | yes | which run this event belongs to |
| `seq` | int | client: omit or 0 | server-assigned, monotonic per run |
| `ts` | string, RFC 3339 UTC | yes | client event time (display & replay) |
| `type` | string | yes | one of §5; unknown types tolerated |
| `schema_version` | int | yes | per §2 |
| `from` | ref or null | per type | origin node (§4) |
| `to` | ref or null | per type | destination node (§4) |
| `payload` | object | per type | type-specific data (§5) |

## 4. Reference grammar

A ref is `kind:id`.

- `kind` ∈ { `agent`, `tool`, `model`, `external`, `state` }
- `id` matches `[a-zA-Z0-9][a-zA-Z0-9._:-]*`
- Models are namespaced by provider: `model:openai:gpt-4o-mini`
- **The same ref string always denotes the same node in the graph.**

| kind | examples |
|---|---|
| agent | `agent:router` · `agent:researcher` · `agent:critic` |
| tool | `tool:web_search` · `tool:calculator` |
| model | `model:openai:gpt-4o-mini` · `model:anthropic:claude-sonnet-4` |
| external | `external:user` · `external:api:stripe` |
| state | `state:memory` · `state:scratchpad` |

## 5. Event types

### 5.1 run_start — from: null, to: null

Marks the beginning of a run. Exactly one per run.

| payload field | type | required | meaning |
|---|---|---|---|
| input | string | yes | the run's initial input (truncated) |
| meta | object | yes | `sdk_version`, `framework`, `language`, optional `store_full` (bool, default false) |

```json
{
  "run_id": "8f1c2e5b-9a4d-4f2b-9c3e-1a2b3c4d5e6f",
  "seq": 0,
  "ts": "2025-01-15T10:00:00.000Z",
  "type": "run_start",
  "schema_version": 1,
  "from": null,
  "to": null,
  "payload": {
    "input": "Research RAG evaluation methods and draft a summary.",
    "meta": { "sdk_version": "0.1.0", "framework": "langgraph", "language": "python" }
  }
}
```

### 5.2 run_finish — from: null, to: null

Marks the end of a run.

| payload field | type | required | meaning |
|---|---|---|---|
| output | string | no | final output (truncated) |
| status | string enum | yes | `ok` · `error` · `cancelled` |
| duration_ms | int | no | wall-clock duration |

```json
{
  "run_id": "8f1c2e5b-9a4d-4f2b-9c3e-1a2b3c4d5e6f",
  "ts": "2025-01-15T10:02:41.500Z",
  "type": "run_finish",
  "schema_version": 1,
  "from": null,
  "to": null,
  "payload": { "output": "Summary of RAG evaluation approaches…", "status": "ok", "duration_ms": 161500 }
}
```

### 5.3 agent_start — from: caller ref (or null at run top), to: agent ref

An agent begins executing.

| payload field | type | required | meaning |
|---|---|---|---|
| name | string | yes | human-readable agent name |
| framework | string | no | framework that spawned it |
| model | ref | no | default model if the agent is model-bound |
| input_snippet | string | no | first 8 KB of its input |

```json
{
  "run_id": "8f1c2e5b-9a4d-4f2b-9c3e-1a2b3c4d5e6f",
  "ts": "2025-01-15T10:00:00.100Z",
  "type": "agent_start",
  "schema_version": 1,
  "from": null,
  "to": "agent:router",
  "payload": { "name": "Router", "framework": "langgraph", "model": "model:openai:gpt-4o-mini", "input_snippet": "Research RAG evaluation…" }
}
```

### 5.4 agent_finish — from: agent ref, to: caller ref

| payload field | type | required | meaning |
|---|---|---|---|
| output_snippet | string | no | last 8 KB of output |
| duration_ms | int | no | agent wall-clock time |

```json
{
  "run_id": "8f1c2e5b-9a4d-4f2b-9c3e-1a2b3c4d5e6f",
  "ts": "2025-01-15T10:02:41.400Z",
  "type": "agent_finish",
  "schema_version": 1,
  "from": "agent:router",
  "to": null,
  "payload": { "output_snippet": "Handed off to researcher.", "duration_ms": 161300 }
}
```

### 5.5 llm_call — from: agent ref, to: model ref

One model invocation. This is where cost and latency live.

| payload field | type | required | meaning |
|---|---|---|---|
| provider | string | yes | e.g. `openai`, `anthropic`, `local` |
| model | string | yes | short model name (full ref is the `to`) |
| input_tokens | int | no | prompt tokens |
| output_tokens | int | no | completion tokens |
| latency_ms | int | no | request round-trip |
| cost_usd | number | no | estimated USD cost |
| prompt_snippet | string | no | truncated prompt |
| response_snippet | string | no | truncated completion |

```json
{
  "run_id": "8f1c2e5b-9a4d-4f2b-9c3e-1a2b3c4d5e6f",
  "ts": "2025-01-15T10:00:01.200Z",
  "type": "llm_call",
  "schema_version": 1,
  "from": "agent:router",
  "to": "model:openai:gpt-4o-mini",
  "payload": { "provider": "openai", "model": "gpt-4o-mini", "input_tokens": 412, "output_tokens": 38, "latency_ms": 610, "cost_usd": 0.00018, "prompt_snippet": "Route this request…" }
}
```

### 5.6 tool_call — from: agent ref, to: tool ref

| payload field | type | required | meaning |
|---|---|---|---|
| name | string | yes | tool name |
| input_snippet | string | no | truncated arguments |

```json
{
  "run_id": "8f1c2e5b-9a4d-4f2b-9c3e-1a2b3c4d5e6f",
  "ts": "2025-01-15T10:01:05.000Z",
  "type": "tool_call",
  "schema_version": 1,
  "from": "agent:researcher",
  "to": "tool:web_search",
  "payload": { "name": "web_search", "input_snippet": "{\"query\": \"RAG evaluation benchmarks\"}" }
}
```

### 5.7 tool_result — from: tool ref, to: agent ref

| payload field | type | required | meaning |
|---|---|---|---|
| ok | bool | yes | did the tool succeed |
| latency_ms | int | no | execution time |
| output_snippet | string | no | truncated result |

```json
{
  "run_id": "8f1c2e5b-9a4d-4f2b-9c3e-1a2b3c4d5e6f",
  "ts": "2025-01-15T10:01:06.400Z",
  "type": "tool_result",
  "schema_version": 1,
  "from": "tool:web_search",
  "to": "agent:researcher",
  "payload": { "ok": true, "latency_ms": 1380, "output_snippet": "Top results: …" }
}
```

### 5.8 handoff ★ — from: agent ref, to: agent ref

**Control transfers from one agent to another.** The event necto exists to visualize.
Handoff failures are the #1 silent bug in multi-agent systems — this event makes them visible.

| payload field | type | required | meaning |
|---|---|---|---|
| reason | string | no | why control moved (`needs_research`, `escalate`, …) |
| context_snippet | string | no | the context carried across the handoff |

```json
{
  "run_id": "8f1c2e5b-9a4d-4f2b-9c3e-1a2b3c4d5e6f",
  "ts": "2025-01-15T10:00:02.100Z",
  "type": "handoff",
  "schema_version": 1,
  "from": "agent:router",
  "to": "agent:researcher",
  "payload": { "reason": "needs_web_research", "context_snippet": "Find papers on RAG evals…" }
}
```

### 5.9 message — from: agent ref, to: agent ref

Content exchanged between agents that does **not** transfer control (peer-to-peer communication).

| payload field | type | required | meaning |
|---|---|---|---|
| content_snippet | string | yes | truncated message body |
| intent | string | no | free-form semantic tag |

### 5.10 state_write — from: agent ref, to: state ref

| payload field | type | required | meaning |
|---|---|---|---|
| key | string | yes | state key touched |
| value_snippet | string | no | truncated value |

### 5.11 error — from: source ref, to: null

| payload field | type | required | meaning |
|---|---|---|---|
| message | string | yes | error message |
| stack | string | no | truncated stack trace |
| recoverable | bool | no | did the run recover |

### 5.12 score — from: null, to: target ref — **RESERVED for v2. Do not emit in v1.**

| payload field | type | required | meaning |
|---|---|---|---|
| name | string | yes | metric name (`faithfulness`, `latency_p95`, …) |
| value | number | yes | numeric score |

---

## 6. Transport limits

- `POST /v1/runs/{id}/events` accepts up to **1000 events** per request.
- Max **64 KB** per event (envelope + payload).
- All `*_snippet` fields are truncated to **8 KB** server-side.
- Opt-in full retention: set `meta.store_full = true` in `run_start` to persist untruncated content.

## 7. Graph projection (normative)

**Nodes** — node id = ref; kind = ref prefix. Created on first appearance in `from` or `to`.
Node attributes: kind, name (from payload when available), framework, accumulated `cost_usd`, `error_count`.

**Edges** — one directed edge per (from, to) pair:

| event | edge | accumulated attrs |
|---|---|---|
| llm_call | agent → model | tokens, latency_ms, cost_usd |
| tool_call | agent → tool | calls |
| tool_result | tool → agent | results |
| handoff | agent → agent, **kind=handoff** | handoffs |
| message | agent → agent, kind=message | messages |
| state_write | agent → state | writes |
| error | attaches to source node; per-edge error_rate derived | — |

- **Per-run graph**: events filtered by `run_id`; timestamps retained for live animation and replay.
- **Topology**: union across all runs; weight = event counts; edge error_rate = attributed errors / total events on that pair.
- **Product rule**: handoff edges MUST render visually distinct (dashed + pulsing in live mode) — projection marks them `kind=handoff` so the UI can honor this without heuristics.

## 8. Adapter mapping (informative)

| LangGraph event | necto type |
|---|---|
| graph invoked / completed | run_start / run_finish |
| `on_chain_start` on an agent node | agent_start |
| `on_chat_model_start` | llm_call |
| `on_tool_start` / `on_tool_end` | tool_call / tool_result |
| channel/state update | state_write |
| conditional edge crossing agent boundary | handoff |
| `on_chain_error` | error |

| OpenAI Agents SDK event | necto type |
|---|---|
| `Runner.run` lifecycle | run_start / run_finish |
| `AgentHooks.on_start` | agent_start |
| model invocation (stream/response events) | llm_call |
| `ToolHooks` | tool_call / tool_result |
| `HandoffOutputItem` / handoff occurred | handoff ★ |
| exception | error |

## 9. Reserved for future

`score` (v2 evals) · `share` (v2 sharing) · `route` / `register` (v3 mesh layer).
Reserved names must not be emitted by third parties without a schema major bump.
