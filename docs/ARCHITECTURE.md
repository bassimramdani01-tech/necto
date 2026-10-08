# necto — Architecture (v1)

Status: **MVP design** · Companion docs: [SPEC.md](../SPEC.md) (vision) · [PLAN.md](../PLAN.md) (step-by-step build plan)

---

## 1. System overview

```
┌───────────────────────── INSTRUMENTATION ─────────────────────────┐
│  Your agent app (LangGraph / OpenAI Agents / any framework)      │
│        │                                                          │
│  necto-sdk (Python): capture → normalize → buffer → batch → POST │
│        │                       (fallback: OTel OTLP or raw JSON) │
└────────┼──────────────────────────────────────────────────────────┘
         ▼
┌─────────────────────────── INGESTION & COMPUTE ───────────────────┐
│  necto-server (FastAPI)                                          │
│   · Ingestion API (validate, seq, store)                         │
│   · Graph projection service (events → nodes/edges)              │
│   · Stats rollups · Live pub/sub hub (WebSocket)                 │
│        │                                                          │
│  PostgreSQL 16 (events as JSONB, append-only)                    │
└────────┼──────────────────────────────────────────────────────────┘
         ▼
┌────────────────────────────── PRESENTATION ───────────────────────┐
│  necto-web (React + @xyflow/react)                               │
│   · Live interactive agent graph · replay timeline scrubber      │
│   · Edge/node inspector · stats dashboard · system topology      │
└───────────────────────────────────────────────────────────────────┘
```

---

## 2. Design principles

1. **Framework-agnostic core.** The server knows nothing about LangGraph or OpenAI. Everything is the neutral event schema (§4).
2. **Events are the only truth.** Append-only event log. The graph is *computed* from events, never stored — so replay, diff, and future features fall out for free.
3. **Align with OpenTelemetry** GenAI/Agent semantic conventions where they exist; don't invent a competing standard.
4. **Self-host first.** One `docker compose up`, one port, seeded demo data. Zero config to the first "wow".
5. **Read-only observer in MVP.** Extension seams (§11) are reserved for the v3 read-write mesh layer.

---

## 3. Components

### 3.1 necto-sdk (Python package `necto-sdk`)
Captures framework activity *inside* the user's app, normalizes it, and ships it out.

| Module | Responsibility |
|---|---|
| `events.py` | Pydantic v2 models for every event type (§4) — the schema in code |
| `tracer.py` | Ring buffer + background sender; flush on 64 events or 100 ms; retry with backoff; **never crashes the host app** (drop + log on failure) |
| `transport/http.py` | Batched POST to the ingestion API (primary) |
| `transport/otel.py` | OTLP emission as an *optional extra* |
| `adapters/langgraph.py` | Hooks LangGraph callbacks → necto events |
| `adapters/openai_agents.py` | Hooks OpenAI Agents SDK traces/handoffs → necto events |
| `adapters/generic.py` | Manual API for anything else (also usable from any language) |

### 3.2 necto-server (FastAPI)
| Module | Responsibility |
|---|---|
| `api/ingestion.py` | Create run, append event batches, finish run |
| `api/query.py` | Runs, events, graph, topology, stats |
| `api/live.py` | WebSocket fan-out hub |
| `models/` | SQLAlchemy: `Run`, `Event`, `Agent`, `Model` |
| `services/graph.py` | **The heart.** Projects events → nodes/edges, per-run and aggregate topology |
| `services/stats.py` | Cost/latency/error rollups |
| `services/live.py` | In-process pub/sub (single-node MVP) |
| `seed/demo.py` | Synthetic demo run, loaded on first boot |

### 3.3 necto-web (React SPA)
| View | What it does |
|---|---|
| **Runs** | List of runs, status, quick stats |
| **Run** | Live graph + timeline scrubber + inspector panel |
| **System** | Aggregate topology across all runs |
| **Stats** | Cost/latency/error charts (Recharts) |
| **Diff** (v2) | Side-by-side run comparison |

### 3.4 Demo generator
`scripts/demo.py` produces a rich synthetic run — router → researcher (with tool calls) → writer → critic handoff loop, **including one intentional silent handoff failure** so the debugging value is visible in the demo.

---

## 4. Event schema v1 — the contract

Every event carries: `run_id`, `seq` (server-assigned), `ts`, `type`, `schema_version`, plus type-specific `from` / `to` references (`"kind:id"`, e.g. `"agent:router"`, `"model:openai:gpt-4o-mini"`, `"tool:web_search"`, `"external:user"`).

| type | from | to | key payload |
|---|---|---|---|
| `run_start` | — | — | `input`, `meta` (sdk_version, framework) |
| `run_finish` | — | — | `output`, `status` |
| `agent_start` | caller | agent | `name`, `framework`, `model` (if fixed) |
| `agent_finish` | agent | caller | `output_snippet` |
| `llm_call` | agent | model | `provider`, `model`, `input_tokens`, `output_tokens`, `latency_ms`, `cost_usd`, `prompt_snippet` |
| `tool_call` | agent | tool | `name`, `input_snippet` |
| `tool_result` | tool | agent | `ok`, `latency_ms`, `output_snippet` |
| `handoff` ★ | agent | agent | `reason`, `context_snippet` — *the killer event: control transfer* |
| `message` | agent | agent | `content_snippet`, `intent` |
| `state_write` | agent | state | `key`, `value_snippet` |
| `error` | source | — | `message`, `stack` (truncated) |
| `score` (v2) | — | target | `name`, `value` |

Example:

```json
{
  "run_id": "r_01", "ts": "2025-01-15T10:00:01.200Z", "type": "handoff",
  "from": "agent:router", "to": "agent:researcher",
  "payload": { "reason": "needs_web_research", "context_snippet": "Find papers on RAG evals…" }
}
```

### Graph projection rules (`services/graph.py`)
- **Nodes** = unique `from`/`to` references, typed: `agent`, `tool`, `model`, `external` (user, state, api).
- **Edges** = direction + count weight per pair: `llm_call` → agent→model; `tool_call`/`tool_result` → agent↔tool; `handoff`/`message` → agent→agent. Handoffs get a distinct visual treatment.
- **Per-run graph** = events of one run with timestamps (for live animation/replay).
- **Topology** = union across runs, weights = total counts, per-edge error rate, per-node cost totals.

---

## 5. Data model (PostgreSQL 16)

```
runs    (id uuid PK, name, status, schema_version, sdk_version,
         framework, meta jsonb, started_at, finished_at, created_at)
events  (id bigserial PK, run_id FK, seq int, ts timestamptz, type text,
         from_ref text, to_ref text, payload jsonb, created_at)
         INDEX (run_id, seq)
agents  (ref text PK, name, kind, framework, first_seen, last_seen, meta jsonb)  -- upserted
models  (ref text PK, provider, name, first_seen, last_seen)                     -- upserted
```

Snippets (prompt/response content) are truncated to 8 KB by default; full-content storage is an opt-in flag per run. Retention is unbounded in MVP (documented dev tool); TTL is v2.

---

## 6. API surface

**Ingestion**
- `POST /v1/runs` — create run → id
- `POST /v1/runs/{id}/events` — append batch → `{accepted, last_seq}`
- `POST /v1/runs/{id}/finish` — `{output, status}`

**Query**
- `GET /v1/runs` · `GET /v1/runs/{id}` · `GET /v1/runs/{id}/events?after_seq=`
- `GET /v1/runs/{id}/graph` → `{nodes, edges}` snapshot
- `GET /v1/topology` → aggregate system graph
- `GET /v1/stats?scope=run|all` → cost/latency/error rollups
- `GET /v1/agents` · `GET /v1/models`

**Live**
- `WS /v1/live/runs/{id}` — pushes each new event (and its node/edge patches) as it lands

**Meta** — `GET /healthz`

---

## 7. All interaction flows

**F1 · Instrument once.** Dev adds 3 lines (`tracer = Necto(langgraph_cb)`). SDK captures framework callbacks → normalizes to events → buffers → POSTs batches → server validates (Pydantic), assigns `seq` in one transaction, stores, publishes to WS hub → SDK receives ack. On 401/5xx: retry with backoff, then drop + log — the user's app never fails because of necto.

**F2 · Live watch.** User opens a running conversation → UI subscribes to WS → agent nodes appear on `agent_start` → edges animate on `llm_call`/`tool_call` → handoffs pulse in a distinct color → token/cost counters tick up in the inspector.

**F3 · Replay.** Open a finished run → UI fetches all events → timeline scrubber rebuilds the graph at time `t` by deterministically applying events up to `t`.

**F4 · Inspect.** Click a node/edge → filtered events → side panel: prompt/response snippets, tokens, latency, cost, raw JSON.

**F5 · System topology.** `GET /v1/topology` → static weighted graph of the whole system → click an agent → its recent runs.

**F6 · Stats.** Per-agent / per-model cost & latency charts; per-edge error rates (handoff failures surface here).

**F7 · Zero-SDK ingest (any language).** Any app POSTs hand-translated events; docs show the mapping table for framework X. This is the interoperability escape hatch.

**F8 · OTel path.** Apps emitting OTel GenAI spans hit the OTLP HTTP receiver; the server translates spans → necto events.

**F9 · Self-host boot.** `docker compose up` → migrations → demo run seeded (env `NECTO_SEED=1`, default on) → open :8000 → click "Demo run" → full graph with zero config.

**F10 · Diff (v2).** Pick runs A/B → align events by (type, from, to) → diff payloads (model, prompt, latency, cost) side-by-side.

**F11 · Mesh layer (v3, reserved).** A message bus where heterogeneous agents *actually* coordinate through necto. Requires addressing, auth, reliability — out of MVP scope, but `handoff`/`message` events already carry the semantics so the schema survives the evolution.

---

## 8. Use cases → feature map

| # | Use case | Served by |
|---|---|---|
| UC1 | "What does my system actually look like?" | System view (F5), topology projection |
| UC2 | "Watch it think in real time" | Live graph (F2) |
| UC3 | "Replay & debug a weird conversation" | Replay scrubber (F3) |
| UC4 | "Where did that handoff go wrong?" | Inspector (F4) + error rates (F6) |
| UC5 | "Which agent/model burns my tokens?" | Stats (F6) |
| UC6 | "Why did behavior change after my edit?" | Diff (F10, v2) |
| UC7 | "I use a framework you don't support" | Generic JSON (F7) / OTel (F8) |
| UC8 | "Try it in 30 seconds" | Seed + compose (F9) |

---

## 9. Tech stack (exact choices)

| Layer | Choice | Why |
|---|---|---|
| SDK | Python 3.10+ · Pydantic v2 · httpx | Same ecosystem as agent frameworks; typed schema |
| Server | Python 3.12 · FastAPI · uvicorn · SQLAlchemy 2 + psycopg3 · Alembic | Fast, typed, native WebSocket, huge OSS familiarity |
| DB | PostgreSQL 16 (`postgres:16-alpine`) | JSONB for events, indexes for seq scans |
| Web | React 19 · TypeScript 5 · Vite 6 · **@xyflow/react 12** (React Flow) · TanStack Query 5 · Zustand 5 · Tailwind CSS 4 · Recharts 2 | React Flow is *the* interactive graph library; Query+Zustand keep live updates sane |
| Live | FastAPI native WebSocket | One server, no extra infra |
| Py tooling | **uv** (env+packages) · Ruff (lint/format) · pytest | Modern, fast, zero config fights |
| JS tooling | **pnpm** · ESLint 9 · Prettier · Vitest · Playwright | Playwright also records the README demo GIF |
| Ship | Docker + Compose v2 · GitHub Actions · MIT license · shields.io badges | One-command self-host; CI: ruff + pytest + tsc + docker build |

---

## 10. Performance targets (MVP)

- Ingestion ≥ 500 events/sec per run (batched inserts)
- UI smooth at ~300 nodes / ~600 edges (React Flow virtualization)
- Event batches ≤ 64 events or 100 ms flush — latency under 1 s to screen in live mode

---

## 11. Extension points (future-proof seams)

- `adapters/` — new framework = one new module
- `transport/` — new destinations (OTLP done; webhook/export later)
- `services/graph.py` projection rules — where v3 mesh/routing semantics land
- `services/live.py` hub — swap in Redis pub/sub for multi-node/cloud
- Auth middleware slot — reserved, unused in MVP

---

## 12. Explicitly deferred (not in MVP)

TypeScript SDK (JS users use F7 generic JSON) · auth/RBAC · Redis pub/sub · retention/TTL · shares/embeds · read-write control · eval scoring · ClickHouse scale-out.
