# necto

> *necto* — Latin: "I bind, I connect, I join."

Open-source observability that renders multi-agent AI systems as a **live, explorable network graph** — who called whom, with which model, at what cost, and where the handoffs broke.

**Status: backend Phase 1 complete and hardened.** The ingestion, graph projection, query and live-streaming APIs work, are performance-tuned, and are covered by **64 tests**. Next up: the Python SDK and the web UI.

## Docs

- [SPEC.md](SPEC.md) — vision and positioning
- [PLAN.md](PLAN.md) — step-by-step build plan
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design
- [docs/SCHEMA.md](docs/SCHEMA.md) — event schema v1 (the contract)
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — developer environment setup
- [docs/HANDOFF.md](docs/HANDOFF.md) — project handoff & status report (read this first)

## Quickstart

*Coming with the first release.*

### Authentication

Auth is **off by default** (local development). Set `NECTO_API_KEY` to require an `X-API-Key`
header on every `/v1` endpoint, including the live WebSocket:

```bash
NECTO_API_KEY=my-secret uv run uvicorn necto_server.main:app
```

`GET /`, `GET /healthz` and `/docs` stay public.

### Pagination

`GET /v1/runs` returns an `X-Total-Count` header with the unpaginated total, so clients can render
"page 2 of 7".

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

### Backfill agent/model registries

The registries are populated at ingest time. For data written before that existed:

```bash
cd server
uv run python scripts/backfill_registries.py
```

It is idempotent — safe to run repeatedly.
