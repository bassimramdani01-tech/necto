# necto

> *necto* — Latin: "I bind, I connect, I join."

Open-source observability that renders multi-agent AI systems as a **live, explorable network graph** — who called whom, with which model, at what cost, and where the handoffs broke.

**Status: backend Phase 1 complete.** The ingestion, graph projection, query and live-streaming APIs are working and covered by 39 tests. The SDK and web UI are next.

## Docs

- [SPEC.md](SPEC.md) — vision and positioning
- [PLAN.md](PLAN.md) — step-by-step build plan
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design
- [docs/SCHEMA.md](docs/SCHEMA.md) — event schema v1 (the contract)
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — developer environment setup
- [docs/HANDOFF.md](docs/HANDOFF.md) — project handoff & status report (read this first)

## Quickstart

*Coming with the first release.*

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