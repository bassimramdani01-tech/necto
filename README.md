# necto

> *necto* — Latin: "I bind, I connect, I join."

**necto draws a map of your AI system.** Point it at an app built from multiple agents, models and tools, and it renders the whole thing as one interactive network graph — so you can see how your AI actually works, instead of piecing it together from logs.

![tests](https://img.shields.io/badge/tests-64%20passing-brightgreen)
![python](https://img.shields.io/badge/python-3.12%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

---

## The goal

> **Make it easy for developers to map out their AI architecture — so the problems and workflows inside it become something you can *see*, not something you have to guess.**

Multi-agent systems *are* graphs: one agent hands work to another, calls a model, uses a tool, passes the result back. But we build and debug them like lists — reading logs line by line, holding the wiring in our heads.

necto gives that graph a face. It is a **map of your AI architecture**: agents, models and tools as nodes, and the calls, tool uses and handoffs between them as edges. Click any connection and see what actually travelled over it.

## The problem it solves

Once a system has more than a couple of agents, the important information stops being visible:

- **You can't see the shape of your system.** Which agent calls which? Where does control change hands?
- **Workflows are invisible.** The path a request takes — agent → model → tool → another agent — only exists in code.
- **Failures are silent.** A routing agent sends work to the wrong place and nothing tells you until the final answer is wrong.
- **Cost and time are opaque.** The bill is a single number; it never says *which agent or which model* is burning it.
- **Every framework hides it differently.** LangGraph, the OpenAI Agents SDK and hand-rolled code each trace their own way — or not at all.

## What necto gives you

- **A live network graph** — agents, models and tools as nodes; calls, tool uses and handoffs as edges.
- **Click any connection** to see exactly what crossed it: the model, token counts, cost, latency.
- **Handoffs highlighted.** Control passing from one agent to another is the most common silent failure, so those edges are marked distinctly.
- **Your whole system, not a single trace.** An aggregate topology across every run, plus per-run detail.
- **Live streaming.** Watch the graph build itself while your agents work.
- **Cost, tokens and latency broken down** per agent and per model — so "which agent is expensive?" has an answer.

## Who it's for

Anyone building with more than one agent or model: indie developers prototyping agent pipelines, teams debugging a multi-agent workflow, and curious people who want to see how their favourite agent framework actually behaves.

No framework lock-in is required by design — the schema is neutral and every framework translates into it.

## Where it is today

necto is **early**. The backend is complete and tested; the SDK and the visual UI are the next milestones.

| Piece | Status |
|---|---|
| Ingestion API, graph projection, query + stats, live streaming | ✅ built · 64 tests |
| Python SDK (auto-instrument your app) | ⬜ next — for now events are posted by hand |
| Visual graph UI | ⬜ next — today the graph is JSON |
| LangGraph / OpenAI Agents adapters | ⬜ planned |
| Self-host via `docker compose` | ⚠️ written, not yet run end-to-end |

Being early means the fastest way to help is to try it, break it, and open an issue.

---

## Docs

- [SPEC.md](SPEC.md) — vision and positioning
- [PLAN.md](PLAN.md) — step-by-step build plan
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design
- [docs/SCHEMA.md](docs/SCHEMA.md) — event schema v1 (the contract)
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — developer environment setup
- [docs/HANDOFF.md](docs/HANDOFF.md) — project handoff & status report

## Quickstart

Start the backend (see [Development](#development)), then:

```bash
# 1. start a run — the response contains the run id
curl -s -X POST http://127.0.0.1:8000/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{"name": "demo"}'

# 2. copy the id from the response, then send events
curl -s -X POST http://127.0.0.1:8000/v1/runs/<RUN_ID>/events \
  -H 'Content-Type: application/json' \
  -d '{"events": [
    {"ts": "2025-01-15T10:00:00Z", "type": "agent_start", "schema_version": 1,
     "to": "agent:router", "payload": {"name": "Router"}},
    {"ts": "2025-01-15T10:00:01Z", "type": "handoff", "schema_version": 1,
     "from": "agent:router", "to": "agent:researcher",
     "payload": {"reason": "needs_research"}}
  ]}'

# 3. inspect the network
curl -s http://127.0.0.1:8000/v1/runs/<RUN_ID>/graph
```

Interactive API docs: <http://127.0.0.1:8000/docs>

> The Python SDK and the visual UI don't exist yet — for now events are posted by hand.

## Development

Full setup: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

### Database

```bash
docker compose up -d db
```

Or run the portable PostgreSQL stand-in described in the development guide.

### Server

```bash
cd server
uv sync                      # install dependencies
uv run alembic upgrade head  # create / upgrade the schema
uv run uvicorn necto_server.main:app --reload
```

Then open <http://127.0.0.1:8000/healthz> — expect:

```json
{"status": "ok", "database": "up", "version": "0.1.0"}
```

### Tests and lint

```bash
cd server
uv run pytest -q
uv run ruff check && uv run ruff format --check
```

### Backfill agent/model registries

The registries are populated at ingest time. For data written before that existed:

```bash
cd server
uv run python scripts/backfill_registries.py
```

It is idempotent — safe to run repeatedly.

## API (v1)

Served by the FastAPI app in `server/`.

### Ingestion

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/runs` | Create a run |
| `POST` | `/v1/runs/{id}/events` | Append a batch of events (server assigns `seq`) |
| `POST` | `/v1/runs/{id}/finish` | Mark a run finished |

### Graph

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/runs/{id}/graph` | Per-run network: nodes + edges |
| `GET` | `/v1/topology` | Aggregate network across all runs |

### Query

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/runs` | List runs with summaries (`?status=`, `limit`, `offset`) |
| `GET` | `/v1/runs/{id}` | Run detail |
| `GET` | `/v1/runs/{id}/events` | Page through events (`?after_seq=`, `limit`) |
| `GET` | `/v1/stats` | Cost / tokens / latency rollups (`?run_id=`) |
| `GET` | `/v1/agents` | Agent registry |
| `GET` | `/v1/models` | Model registry |

### Live

| Protocol | Path | Purpose |
|---|---|---|
| `WS` | `/v1/live/runs/{id}` | Stream new events and run-finished notices |

### Authentication

Auth is **off by default** (local development). Set `NECTO_API_KEY` to require an
`X-API-Key` header on every `/v1` endpoint, including the live WebSocket:

```bash
NECTO_API_KEY=my-secret uv run uvicorn necto_server.main:app
```

`GET /`, `GET /healthz` and `/docs` stay public.

### Pagination

`GET /v1/runs` returns an `X-Total-Count` header with the unpaginated total, so clients can
render "page 2 of 7".
