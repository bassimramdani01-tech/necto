# Changelog

All notable changes are recorded here. This project follows semantic versioning
once it reaches 1.0; until then, minor versions may change behavior.

## 0.1.0 (pre-release, unreleased)

The first end-to-end version: record agent runs, explore the graph, replay them, and self-host it.

### Backend

- Frozen event schema v1: 12 event types, `kind:id` refs, batched ingestion with server-assigned `seq`.
- Graph computed from events: agents, models, tools, states, external refs, handoff/tool/error edges.
- Query API: runs with search, framework filter, sorting and pagination; per-run detail, events
  pages, graph, topology, stats, agent/model registries, distinct frameworks.
- Live streaming over WebSocket with gap-free subscribe/hello/drain sequencing.
- Optional API key (`NECTO_API_KEY`) for ingestion and live sockets.
- Demo seeding on first boot (`NECTO_SEED=1`).

### Python SDK

- Zero-dependency tracer with background flushing, atexit flush, idempotent close, and
  `Necto.from_env()`.
- Adapters for LangGraph/LangChain, OpenAI Agents SDK and OpenTelemetry (duck-typed, optional).
- HTTP transport with retries, including `429` + `Retry-After`; never raises into the host app.

### Web UI

- Runs dashboard (search, filters, sorting, "load more"), graph, live mode, replay scrubber,
  inspector with copy-JSON and jump-to-event, stats (lazy-loaded), topology view.
- URL-addressable state (`?run=`, `?at=`, `?node=`, `?edge=`, `?view=`, `?status=`).
- Responsive shell, keyboard focus styles, reduced-motion support.

### Self-host

- `docker compose up -d --build` serves API + built UI + Postgres on `http://localhost:8000`.
- `scripts/dev.ps1` for local development, `scripts/reset.py` to reset/seed the database.

### Tooling

- 176 tests: 84 server, 61 SDK, 31 web. Repo-wide ruff + pre-commit; CI workflow and PyPI trusted
  publishing workflow.
