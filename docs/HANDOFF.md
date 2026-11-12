# necto — Handoff & Status Report

> **Snapshot:** end of backend Phase 1. This document is the single source of truth for
> "what exists, how to run it, what is broken, and what to do next."
> Read this first when resuming the project.

---

## 0. TL;DR

- **Vision:** an open-source tool that renders multi-agent AI systems as a **live, explorable network graph** — who called whom, with which model, at what cost, and where handoffs broke.
- **Backend Phase 1 is COMPLETE** — ingestion, graph projection, query, and live WebSocket streaming all work, verified against real PostgreSQL 16.4.
- **39 automated tests pass.** No migration drift. Working tree clean.
- **Not yet built:** the SDK (Phase 2) and the visual UI (Phase 3) — those are what make it *usable*.
- **Known bugs:** 4 confirmed, all documented in §5 with fixes. None block starting Phase 2, but fix them first (§6.1).

---

## 1. What necto is

`necto` (Latin: *I bind, I connect, I join*) ingests events from agents and models as they work together, then
projects them into a graph of nodes (agents, models, tools) and edges (calls, handoffs, messages).

The core bet from the spec: **treat the *system of agents* as the first-class object, not a linear trace.**
The graph is *computed* from an append-only event log — never stored — so replay, diffing and topology
aggregation fall out for free.

- Positioning & vision: [SPEC.md](../SPEC.md)
- Build plan: [PLAN.md](../PLAN.md)
- System design: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Event contract (frozen v1):** [SCHEMA.md](SCHEMA.md)
- Environment setup: [DEVELOPMENT.md](DEVELOPMENT.md)

---

## 2. Status at a glance

| Area | State | Notes |
|---|---|---|
| Event schema v1 | ✅ Frozen | 12 event types, versioning policy, projection rules |
| Ingestion API | ✅ Done | Batched events, race-safe seq assignment, truncation |
| Graph projection | ✅ Done | Per-run graph + aggregate topology |
| Query API | ✅ Done | Runs, event paging, stats, registries |
| Live WebSocket | ✅ Done | Push new events + run-finished notices |
| Agent/model registries | ✅ Done | Upserted on every ingest |
| **SDK (Python)** | ⬜ Not started | **Phase 2 — the next milestone** |
| **Web UI** | ⬜ Not started | Phase 3 |
| Demo data + README GIF | ⬜ Not started | Phase 4 |
| Docker self-host | ✅ Verified | `docker compose up -d db` → healthy PostgreSQL 16.15; migrations + 64 tests pass against it |
| CI | ⬜ Not started | Phase 5 |
| Auth | ✅ Done | Optional §BT§NECTO_API_KEY§BT§ → §BT§X-API-Key§BT§ on all /v1 endpoints incl. WS |

**Metrics:** 10 commits · 2,006 lines of Python · 39 tests · 4 tables.

---

## 3. What we built

### 3.1 Repository layout

```
necto/
├── SPEC.md                  # vision, positioning, differentiation
├── PLAN.md                  # 26-step build plan across 6 phases
├── README.md                # landing page + API reference + dev instructions
├── LICENSE                  # MIT
├── docker-compose.yml       # postgres:16-alpine (for self-host)
├── .env.example             # config template
├── .pre-commit-config.yaml  # ruff + prettier
├── docs/
│   ├── ARCHITECTURE.md      # system design, all interaction flows
│   ├── SCHEMA.md            # FROZEN event schema v1 (the contract)
│   ├── DEVELOPMENT.md       # environment setup (toolchain + Docker steps)
│   └── HANDOFF.md           # this file
└── server/                  # FastAPI backend
    ├── pyproject.toml       # deps + pytest config
    ├── alembic.ini
    ├── alembic/             # migrations (initial schema)
    ├── necto_server/
    │   ├── config.py        # pydantic-settings (NECTO_* env vars)
    │   ├── db.py            # engine, session, Base
    │   ├── models.py        # SQLAlchemy: Run, Event, Agent, Model
    │   ├── main.py          # app factory, /healthz, router registration
    │   ├── api/             # runs.py, graph.py, query.py, live.py
    │   ├── schemas/         # events.py, graph.py, query.py
    │   └── services/        # ingestion.py, graph.py, queries.py, live.py
    └── tests/               # 39 tests across 6 files
```

### 3.2 Event schema v1 (frozen — do not break)

Every event has: `run_id`, `seq` (server-assigned), `ts`, `type`, `schema_version`, `from`/`to` refs, `payload`.

Refs use `kind:id` — kinds: `agent`, `tool`, `model`, `external`, `state`
(e.g. `agent:router`, `model:openai:gpt-4o-mini`, `tool:web_search`).

The 12 event types:

| Type | from → to | Purpose |
|---|---|---|
| `run_start` | — | Begins a run; carries input + meta |
| `run_finish` | — | Ends a run; status + output |
| `agent_start` | caller → agent | Agent begins work |
| `agent_finish` | agent → caller | Agent done |
| `llm_call` | agent → model | Model invocation: tokens, cost, latency |
| `tool_call` | agent → tool | Tool used |
| `tool_result` | tool → agent | Tool returned |
| **`handoff`** ★ | agent → agent | **Control transfer — necto's reason for existing** |
| `message` | agent → agent | Peer message (no control transfer) |
| `state_write` | agent → state | External state touched |
| `error` | source | Failure (attributed to node + last edge) |
| `score` | — | **Reserved for v2 — do not emit** |

Versioning: additive changes are compatible; breaking changes need a major bump. Unknown event types
are stored verbatim (forward compatibility). `schema_version` is required.

### 3.3 Server modules and what they own

| Module | Responsibility |
|---|---|
| `services/ingestion.py` | Validation, per-type payload models, snippet truncation, **race-safe seq assignment** (`SELECT … FOR UPDATE`), registry upserts, publish to live hub |
| `services/graph.py` | Events → nodes/edges; node metadata enrichment; error attribution to last edge; per-run + topology |
| `services/queries.py` | Run summaries, event paging, stats rollups (by model / agent / type), registries |
| `services/live.py` | In-process pub/sub hub; thread-safe fan-out from sync handlers to async sockets |
| `api/live.py` | WebSocket endpoint: hello → stream events → heartbeat ping |

### 3.4 API surface (v1)

**Ingestion**
- `POST /v1/runs` → create run
- `POST /v1/runs/{id}/events` → append batch (max 1000 events, 64 KB each)
- `POST /v1/runs/{id}/finish` → end run

**Graph**
- `GET /v1/runs/{id}/graph` → per-run nodes + edges
- `GET /v1/topology` → aggregate across all runs

**Query**
- `GET /v1/runs` (`?status=`, `limit`, `offset`)
- `GET /v1/runs/{id}`
- `GET /v1/runs/{id}/events` (`?after_seq=`, `limit`)
- `GET /v1/stats` (`?run_id=`)
- `GET /v1/agents` · `GET /v1/models`

**Live**
- `WS /v1/live/runs/{id}` → `hello`, `events`, `run_finished`, `ping`

**Meta**
- `GET /` · `GET /healthz` · `GET /docs` (Swagger)

### 3.5 Tests — 39 passing

| File | Count | Covers |
|---|---|---|
| `test_health.py` | 2 | App + DB health |
| `test_ingestion.py` | 11 | Seq assignment, validation, truncation, finish guard |
| `test_graph.py` | 8 | Nodes/edges, handoff marking, error attribution, topology |
| `test_query.py` | 14 | Run list/detail, paging, stats, registries |
| `test_live.py` | 6 | WebSocket hello/events/finished, resume, unknown run |

Tests run against an **isolated `necto_test` database** (created automatically by `conftest.py`), so dev data is never touched.

### 3.6 Commit history

```
07e3c31 feat(server): live WebSocket streaming + document v1 API surface
12ce4a6 feat(server): query API — run list/detail, event paging, stats rollups, agent/model registries
aef6a26 feat(server): graph projection — events to nodes/edges, per-run and topology endpoints
885e10b feat(server): ingestion API — run lifecycle, batched events, sequence assignment, validation
7e24d28 chore: keep .env.example tracked
80caf6c feat(server): FastAPI skeleton, SQLAlchemy models, initial migration, health checks
50af8f1 docs: use detached Start-Process for local postgres
a57e1ed docs: record actual installed toolchain and manual Docker steps
d5a3006 docs: add developer environment setup guide
0f035dc chore: scaffold necto repo — schema v1, license, docs, templates
```

---

## 4. How to run everything

### 4.1 What is installed

| Tool | Version | Location |
|---|---|---|
| git | 2.55.0 | `C:\Program Files\Git\cmd` |
| uv | 0.13.0 | `%LOCALAPPDATA%\Programs\necto-tools\uv` |
| Python | 3.12.15 (uv-managed) | `%APPDATA%\uv\python\...` |
| PostgreSQL | 16.4 (portable) | `%LOCALAPPDATA%\Programs\necto-tools\pgsql` |
| Node.js | 24.20.0 | `%LOCALAPPDATA%\Programs\necto-tools\node` |
| pnpm | 12.11.2 | same as Node |
| GitHub CLI | 2.102.0 | `%LOCALAPPDATA%\Programs\necto-tools\gh` |
| pre-commit | 4.6.2 | `%USERPROFILE%\.local\bin` |

**Not installed:** Docker Desktop (needs BIOS virtualization + admin — see [DEVELOPMENT.md §2 Option B](DEVELOPMENT.md)).

### 4.2 Start the database

```powershell
& "$env:LOCALAPPDATA\Programs\necto-tools\pgsql\bin\pg_ctl.exe" -D "$env:LOCALAPPDATA\Programs\necto-tools\pgdata" -l "$env:LOCALAPPDATA\Programs\necto-tools\pg.log" start
# check
& "$env:LOCALAPPDATA\Programs\necto-tools\pgsql\bin\pg_isready.exe" -h 127.0.0.1 -p 5432
# stop
& "$env:LOCALAPPDATA\Programs\necto-tools\pgsql\bin\pg_ctl.exe" -D "$env:LOCALAPPDATA\Programs\necto-tools\pgdata" stop
```

Connection string (identical to what Docker will use — swapping is a one-env-var change):

```
postgresql://necto:necto@127.0.0.1:5432/necto
```

> **Agent-session note:** inside the DSH agent sandbox, detached processes are killed when the tool call
> ends. Postgres must run as a **managed background job** there, not via `Start-Process`.

### 4.3 Run the server

```powershell
cd server
uv sync
uv run alembic upgrade head
uv run uvicorn necto_server.main:app --reload
```

Then open <http://127.0.0.1:8000/healthz> → expect `{"status":"ok","database":"up"}`.

### 4.4 Run the tests

```powershell
cd server
uv run pytest -q
```

### 4.5 ⚠️ Environment quirk (important for the next agent session)

In this machine's sandboxed shell, **uv's venv trampoline `python.exe` hangs / access-denied**. Standard
`python -m venv` works fine. Workaround used throughout Phase 1:

```powershell
$base = "$env:APPDATA\uv\python\cpython-3.12.15-windows-x86_64-none\python.exe"
$server = "C:\Users\xxdma\Downloads\necto\server"
$env:PYTHONPATH = "$server\.venv\Lib\site-packages;$server"
Set-Location $server
& $base -m pytest -q
& $base -m alembic upgrade head
& $base -m uvicorn necto_server.main:app --host 127.0.0.1 --port 8000
```

In a **normal user terminal**, `uv run …` should work as documented. If it fails with
*"Failed to spawn: python"*, recreate the venv with `python -m venv .venv`.

---

## 5. Known issues (from the full audit)

### 5.1 Confirmed bugs — ✅ ALL FOUR FIXED (Priority 1 pass, see §10)

| # | Bug | Evidence | Fix |
|---|---|---|---|
| **B1** | `GET /v1/stats` returns **500** when any `llm_call` lacks a `from`/`to` ref | Posted `llm_call` without `to` → accepted 200, then stats → `ValidationError: ByModel.model … input_value=None` | Validate required refs per event type **and** make stats tolerate nulls |
| **B2** | Event refs are **not validated** against the schema grammar | `from: "not-a-ref"`, `to: "also bad!!"` → accepted; became graph node ids | Enforce `kind:id` + allowed kinds → 422 |
| **B3** | `runs.framework` / `runs.sdk_version` **never populated** | Created run with meta framework → detail shows `null` | Set from `meta` in `create_run`; backfill from `run_start` |
| **B4** | WebSocket **race** can drop an event on connect | `api/live.py`: `_load_run_state` (reads last_seq) runs **before** `hub.subscribe` | Subscribe first, then load state; dedupe by `seq` |

All four slipped past 39 green tests — **add regression tests with each fix.**

### 5.2 Problems & gaps

- **No auth** on any endpoint (including WS) — must be addressed before public self-host.
- **`.env` location mismatch** — settings read `./.env` (CWD) but `.env.example` sits at repo root; README says `cd server`. Copying it as documented does nothing.
- **Naive timestamps accepted** — `ts: "2025-01-15T10:00:00"` (no tz) is silently reinterpreted in server timezone.
- **Blind `except Exception: pass`** in `api/live.py` — swallows socket errors without logging.
- **No `[tool.ruff]` config** — lint is version-dependent. Ruff 0.17.3 reports 39 findings (24 auto-fixable); `B008` is a FastAPI false positive needing an ignore. Two real ones: unused imports in `test_graph.py` / `test_query.py`.
- **No total count** on `GET /v1/runs` — client can't render "page 2 of 7".
- **Registry backfill missing** — `/v1/agents` only knows agents ingested since Step ⑦; earlier demo runs are absent.
- **Doc drift** — SCHEMA.md says `*_snippet` fields are truncated; code truncates **all** strings.

### 5.3 Measured performance — ✅ FIXED (Priority 2 pass, see §11)

| Operation | Measured | Projected @ 1M events | Problem |
|---|---|---|---|
| `GET /v1/runs` (limit 50) | 60 ms | ~6 s | aggregates **all** events, not the page |
| `GET /v1/runs/{id}` | 13 ms | ~1.3 s | same full aggregation for one run |
| `GET .../events` (200) | 17 ms | ~17 ms | ✅ indexed |
| `GET .../graph` (100 events) | 6 ms | 6 ms | ✅ per-run only |
| `GET /v1/stats` | 59 ms | ~6 s | expected scan |
| **`GET /v1/topology`** | **723 ms** | **~72 s** | 🔴 loads every event into Python |

**Optimization priorities:**
1. **Topology → SQL aggregation** (`GROUP BY from_ref, to_ref, type`) — biggest win, ~70×.
2. **Constrain run summaries** to the page's run ids (two-step query) → O(page) instead of O(all events).
3. **Denormalized counters** on `runs` (event_count/cost/tokens/errors) updated in the ingest transaction — best long-term.
4. **Add indexes:** `runs.started_at`, `events.type`, `agents.last_seen`, `models.last_seen`.
5. `_event_size` double-serializes — use `model_dump_json()`.

---

## 6. What we want to do next

### 6.1 Priority fixes — ✅ DONE (see §10)

1. Ref validation (grammar + kinds + per-type required refs) → fixes B2
2. Stats tolerates null refs → fixes B1's crash
3. Populate `framework`/`sdk_version` → fixes B3
4. WebSocket subscribe-before-load → fixes B4
5. Regression tests for all four

### 6.2 Performance pass — ✅ DONE (see §11)

SQL-aggregated topology · constrained summaries · 4 indexes (optionally denormalized counters).

### 6.3 Hygiene (~30 min)

`[tool.ruff]` config + fix 39 findings · `.env` location · timestamp normalization · WS logging.

### 6.4 Phase 2 — Python SDK (next milestone)

Per [PLAN.md](../PLAN.md) steps ⑨–⑫:
- **⑨ Core tracer:** buffer/batch/retry, never crash the host app
- **⑩ LangGraph adapter:** callbacks → necto events
- **⑪ OpenAI Agents SDK adapter:** trace hooks + **handoff** capture
- **⑫ Generic JSON / OTel path** for any other framework

Mapping tables already exist in [SCHEMA.md §8](SCHEMA.md).

### 6.5 Phase 3 — Web UI

Per PLAN.md steps ⑬–⑱: Vite/React 19 · **@xyflow/react** graph view · live + replay scrubber ·
node/edge inspector · stats dashboard with Recharts.

### 6.6 Phase 4 — Demo & polish

Demo generator script (router → researcher → writer → critic, with one **intentional silent handoff
failure** so the debugging value is visible) · first-boot seed · Playwright → GIF for the README.

### 6.7 Phase 5 — Publish

GitHub Actions CI · PyPI publish of the SDK · v0.1.0 release · launch posts (r/LocalLLaMA, r/LangChain, Show HN).

### 6.8 Before public self-host

API-key auth (all endpoints incl. WS) · registry backfill · pagination totals · test the
`docker-compose.yml` path end-to-end.

---

## 7. Key decisions (and why)

| Decision | Rationale |
|---|---|
| **Graph computed, not stored** | Replay/diff/topology come free; storage stays simple |
| **Ref grammar `kind:id`** | One node identity across frameworks; provider-namespaced models |
| **Server assigns `seq`** with row lock | Concurrent batches can never collide or reorder |
| **Batches are atomic** | No half-recorded runs |
| **Snippets truncated (8 KB)** with opt-in `store_full` | Protects UI/DB; privacy-friendly default |
| **Unknown event types tolerated** | Future SDK versions can't break old servers |
| **In-process pub/sub** | One process, zero infra for MVP; Redis is the documented scale-out seam |
| **`/finish` does not auto-create a `run_finish` event** | One clear owner per fact; clients may still send the event |
| **Errors attach to node + last edge** | Makes per-connection error rates meaningful |
| **Postgres portable stand-in** | Docker unavailable (BIOS virtualization off); identical connection string |

---

## 8. Open questions

1. Should `/finish` also append a `run_finish` event so the log is always complete? (Currently no.)
2. Registry backfill: ship a one-off script before publishing? (Recommended.)
3. Auth shape: single `NECTO_API_KEY` header vs. per-run tokens?
4. Should `/v1/agents` also list tools (`?kind=` filter) or stay agents-only?
5. Do we keep `necto_test` DB as the test target, or move to ephemeral schemas in CI?

---

## 9. Quick reference

**Event types:** run_start, run_finish, agent_start, agent_finish, llm_call, tool_call, tool_result,
**handoff** ★, message, state_write, error, score *(reserved)*

**Node kinds:** agent · tool · model · external · state

**Edge kinds:** llm_call · tool_call · tool_result · **handoff** · message · state_write

**DB tables:** `runs`, `events` (unique `(run_id, seq)`), `agents`, `models`, `alembic_version`

**Dev databases:** `necto` (dev, has demo data) · `necto_test` (tests, auto-created)

**Current dev data:** 4 runs · 25 events · 3 agents · 1 model

**Health check:** `GET /healthz` → `{"status":"ok","database":"up","version":"0.1.0"}`

---

## 10. Update log

### Priority 1 — correctness fixes (DONE)

All four confirmed bugs from §5.1 are fixed, each with regression tests. **Test count: 39 → 48.**

| Bug | Fix | Where |
|---|---|---|
| **B1** stats 500 on null refs | ${BT}by_model${BT}/${BT}by_agent${BT} exclude rows with NULL refs — legacy/bad rows can no longer 500 the endpoint | ${BT}services/queries.py${BT} |
| **B2** refs not validated | Strict ${BT}kind:id${BT} grammar, allowed kinds, and per-type presence/kind rules from SCHEMA.md §4–5 → ${BT}422${BT} with precise messages | ${BT}schemas/events.py${BT} + ${BT}services/ingestion.py${BT} |
| **B3** framework/sdk_version never stored | Populated from create-time meta **and** backfilled from ${BT}run_start${BT} event meta | ${BT}services/ingestion.py${BT} |
| **B4** live socket connect race | Hub subscribes **before** reading state; events published in the gap are drained after ${BT}hello${BT} with ${BT}seq <= last_seq${BT} duplicates filtered. Socket errors now logged, not swallowed | ${BT}api/live.py${BT} |

**Verified by re-running the original audit probes:**

| Probe | Before | After |
|---|---|---|
| ${BT}GET /v1/stats${BT} after malformed event | 500 (ValidationError) | 200 |
| ${BT}POST${BT} invalid refs (${BT}"not-a-ref"${BT}) | 200 accepted | 422 rejected |
| ${BT}POST llm_call${BT} without ${BT}to${BT} | 200 accepted | 422 rejected |
| ${BT}GET /v1/runs/{id}.framework${BT} | null | "langgraph" |
| Live event during connect window | could be lost | delivered (dedupe unit-tested) |

No regressions: ${BT}store_full${BT} retention still preserves 20 000 chars; ${BT}schema_version${BT} rejection still 400.

### Still open (unchanged)

- **Priority 2** — performance: SQL-aggregated topology, constrained run summaries, 4 indexes (§5.3)
- **Priority 3** — hygiene: ${BT}[tool.ruff]${BT} config, ${BT}.env${BT} location, timestamp normalization
- **Priority 4** — before publishing: auth, registry backfill, pagination totals
- **Phase 2** — Python SDK (do not start until Priorities 1–3 are done)

---

## 11. Update log — Priority 2 (performance)

Measured on **10,000 events / 100 runs**, best of 7 after warmup:

| Operation | Before | After | Gain |
|---|---|---|---|
| `GET /v1/topology` | 723 ms | **87 ms** | **~8×** |
| `GET /v1/runs` (limit 50) | 60 ms | **11 ms** | **~6×** |
| `GET /v1/runs/{id}` | 13 ms | **3 ms** | **~4×** |
| `GET /v1/stats` | 59 ms | **31 ms** | **~2×** |
| `GET .../events` (200) | 17 ms | **9 ms** | ~2× |

("Before" were single-shot cold measurements; "after" are warmed. Warm-vs-warm gains are
~2–4×; the larger headline figures include removing first-load overhead.)

### What changed

1. **Topology aggregates in SQL.** `build_topology` no longer loads every event into Python —
   nodes, edges and totals are grouped in Postgres.
2. **Error attribution moved into SQL** (window function over `(run_id, from_ref)` ordered by
   `seq`). This replaced a query that pulled ~7,500 rows into Python and **fixed a real
   bug**: the old in-memory attribution leaked across runs.
3. **Typed metric columns on `events`** (`cost_usd`, `tokens`, `latency_ms`) extracted at
   ingest and backfilled by migration. No read path parses JSONB any more.
4. **Run summaries aggregate only the page's runs** (`_run_event_aggregates`) instead of the
   entire events table.
5. **Indexes added:** `runs.started_at`, `events.type`, `agents.last_seen`, `models.last_seen`.
6. `_event_size` serialises once (`model_dump_json`) instead of twice.

### Tests: 48 → 52

New: SQL topology parity vs the Python projection, per-run error attribution,
most-recent-edge attribution, topology node names.

### Still open

- Denormalised counters on `runs` (event_count/cost/tokens/errors) so run lists need no aggregate
  query at all.
- Pre-aggregated topology snapshots if event volume grows past ~10⁵.

---

## 12. Update log — Priority 3 (hygiene) & Priority 4 (pre-publish)

### Priority 3 — hygiene (DONE)

- **Ruff configured** in `server/pyproject.toml`: `select = [E,F,I,UP,B,SIM]`, `B008` ignored
  (FastAPI `Depends` in defaults is the documented pattern), line length 100.
  **41 findings auto-fixed, 17 files formatted, 1 manual fix** → `ruff check` and` ruff format --check` both clean.
- **`.env` now resolves from either `server/` or the repo root** (`env_file=(".env", "../.env")`). Before,
  following the docs did nothing.
- **Timestamps are normalised to UTC** on ingest (naive → UTC, aware → converted), and the DB
  session runs with `timezone=UTC` so API responses are deterministic regardless of server zone.
- WebSocket errors are logged rather than swallowed (was already fixed in the Priority 1 pass).

### Priority 4 — pre-publish (DONE)

- **API-key auth** (`necto_server/auth.py`): set `NECTO_API_KEY` to require `X-API-Key` on all
  `/v1` routes **and** the live WebSocket (`401` / close `4401`). `/`, `/healthz` and `/docs` stay public.
  Disabled by default for local development; verified live end-to-end.
- **Registry backfill script** (`server/scripts/backfill_registries.py`): idempotent, re-derives
  agents/models from existing events. Verified on dev data (26 events → 4 agents, 2 models;
  `agent:router` gained its previously-missing name).
- **Pagination totals**: `GET /v1/runs` returns `X-Total-Count` (honours the status filter).
- **Compose drift tests**: `docker-compose.yml` credentials/image are asserted against the code
  defaults, so the self-host stack cannot silently diverge. (Docker itself still isn't installed
  on this machine, so the stack has not been executed end-to-end.)

### Tests: 52 → 64

New: API key (HTTP + WS + public routes), pagination totals, naive-timestamp normalisation,
compose/config drift.

### Remaining before a public release

- CI (GitHub Actions: ruff + pytest against a Postgres service) — Phase 5.
- Phase 2 (SDK) and Phase 3 (web UI) are still unbuilt.

---

## 13. Update log — Phase 2 (Python SDK), step ⑨

**Environment unblocked first.** WSL2 was installed offline (the network blocks Microsoft's delivery
CDN, so `wsl --install` times out; the kernel came from
`wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi` instead). Docker Desktop then
started and the self-host path was verified end-to-end:

- `docker compose up -d db` → `necto-db` **Up (healthy)**, PostgreSQL 16.15
- `alembic upgrade head` → all three migrations applied against the container
- `pytest` → **64 passed** against the container
- live API against the container → `/healthz` 200, `/v1/runs` 200, `/v1/topology` 200

Docker Hub is DNS-poisoned on this network; images pull through `docker.m.daocloud.io` (documented in
`docs/DEVELOPMENT.md`).

**Step ⑨ — core tracer (`sdk/`).**

| File | Purpose |
|---|---|
| `sdk/necto_sdk/events.py` | schema-v1 event/envelope builders, `kind:id` refs, no deps |
| `sdk/necto_sdk/transport.py` | `HttpTransport` (stdlib `urllib`), `RecordingTransport`, `NullTransport` |
| `sdk/necto_sdk/tracer.py` | `Necto` tracer + `Run` handle, batching, background flush |
| `sdk/tests/` | 14 tests |

Design decisions:

- **Zero runtime dependencies** (stdlib only) so the SDK installs anywhere and cannot conflict with
  a user's framework versions.
- **Never crashes the host app**: every transport call is wrapped; failures are logged and dropped.
- **Buffered**: flushes at `batch_size` (default 64) or every `flush_interval` (default 1 s) on a
  daemon thread, so instrumentation adds no latency to the agent loop.
- **No endpoint = no-op**: `Necto()` with nothing configured disables itself instead of failing.
- `RecordingTransport` lets users test their instrumentation without a server.

**Step ⑩ — LangGraph / LangChain adapter (`sdk/necto_sdk/adapters/langgraph.py`).**

- `NectoCallbackHandler` implements the LangChain callback surface (`on_chain_start/end/error`,
  `on_chat_model_start`, `on_llm_end/error`, `on_tool_start/end/error`) and is **duck-typed** — it
  never imports langchain or langgraph, so the module is import-safe without them installed.
- Root chain start creates the necto run; root chain end finishes it. Node chains emit `agent_start`/
  `agent_finish`; a change of node emits `handoff` (heuristic: LangGraph runs nodes in sequence).
  Chat models emit `llm_call` with provider, model, tokens (from `llm_output` or
  `usage_metadata`) and latency; tools emit `tool_call`/`tool_result`.
- `attach(handler, config)` merges the handler into an existing LangChain config.
- Every callback is guarded: an adapter bug can never break the user's graph.
- Verified end-to-end over HTTP against the Docker stack: a simulated 3-node graph produced
  6 nodes / 6 edges, 2 handoffs, 2 model calls (168 + 420 tokens) and 1 tool round-trip.

**Tests:** 15 → 23 (8 adapter tests).

**Step ⑪ — OpenAI Agents SDK adapter (
`sdk/necto_sdk/adapters/openai_agents.py`).**

- ${BT}NectoProcessor${BT} implements the SDK's ${BT}TracingProcessor${BT} interface (${BT}on_trace_start/end${BT},
  ${BT}on_span_start/end${BT}, ${BT}shutdown${BT}, ${BT}force_flush${BT}). ${BT}instrument(necto)${BT} registers it.
- Span mapping: ${BT}agent${BT} → ${BT}agent_start${BT}/${BT}agent_finish${BT}; ${BT}handoff${BT} → ${BT}handoff${BT}; ${BT}generation${BT} → ${BT}llm_call${BT}
  (model, tokens from ${BT}usage${BT}, latency from span timestamps); ${BT}function${BT} → ${BT}tool_call${BT}/${BT}tool_result${BT}.
- Provider is inferred from the model name (gpt/o1 → openai, claude → anthropic, gemini → google).
- Duck-typed: importing the module never imports ${BT}agents${BT}. Only ${BT}instrument()${BT} needs the SDK and raises a
  clear ImportError otherwise (covered by a test).
- Verified end-to-end over HTTP: a simulated trace produced 5 nodes / 5 edges — handoff
  triage→booking, gpt-4o-mini (240 tokens / 520 ms), claude-sonnet-4 (390 tokens / 450 ms) and a
  check_availability tool round-trip (230 ms).

**Tests:** 23 → 31 (8 OpenAI adapter tests).

**Step ⑫ — OpenTelemetry bridge (`sdk/necto_sdk/adapters/otel.py`). Phase 2 complete.**

- `NectoSpanProcessor` implements the OTel `SpanProcessor` interface (`on_start`, `on_end`,
  `shutdown`, `force_flush`); `instrument(necto)` registers it on a `TracerProvider`.
- Understands the GenAI semantic conventions: `gen_ai.operation.name` of `invoke_agent` /
  `chat` / `execute_tool` map to `agent_start`+`agent_finish` / `llm_call` (model, tokens,
  latency from span timestamps) / `tool_call`+`tool_result`. Span status ERROR → `ok=false`.
  `necto.from` + `necto.to` attributes emit an explicit `handoff`.
- The run finishes when the **root span** ends; a change of active agent also emits a handoff.
- Verified end-to-end over HTTP: 5 nodes / 5 edges — handoff triage→booking, gpt-4o-mini
  (210 tokens / 750 ms), claude-sonnet-4 (620 tokens / 900 ms), tool round-trip (300 ms).
- Note: `opentelemetry` turned out to be present in the dev venv, so `instrument()` was tightened
  to raise a clear `RuntimeError` when no SDK `TracerProvider` is configured (the API-level
  `ProxyTracerProvider` has no `add_span_processor`).

### Phase 2 summary (steps ⑨–⑫) — DONE

| Step | Deliverable | Tests |
|---|---|---|
| ⑨ | core tracer: buffered, non-blocking, dependency-free, never raises | 15 |
| ⑩ | LangGraph / LangChain adapter with handoff inference | +8 (23) |
| ⑪ | OpenAI Agents SDK adapter | +8 (31) |
| ⑫ | OpenTelemetry bridge | +11 (42, 1 skipped) |

All three adapters are duck-typed: `import necto_sdk.adapters.*` never imports the framework.
Every adapter was verified end-to-end over HTTP against the Docker stack, not just unit-tested.

**Next: Phase 3 — the visual graph UI** (the core product bet).

---

## 14. Pre-Phase-3 audit (full system check)

Ran before starting the UI, to make sure the foundation is trustworthy.

### What was verified

| Area | Result |
|---|---|
| Docker self-host | container up + healthy, migrations applied |
| Server tests | **64 passed** |
| SDK tests | **51 passed, 1 skipped** |
| Live API surface | **18/18 checks** (health, create, ingest, validation, reads, finish) |
| Validation behaviour | bad ref → 422, bad schema_version → 400, empty batch → 422, unknown run → 404 |
| Live WebSocket (real client) | `hello` → live `events` (seq 1,2) → `run_finished` ✅ |
| SDK end-to-end | framework + sdk_version stored, state node/edge, graph + stats correct |
| `store_full` retention | implemented (ingestion.py) |
| Transport limits | 1000 events / 64 KB / 8 KB snippets — code matches SCHEMA §6 |
| TODO / FIXME / stubs | none |

### Fixes applied during the audit

1. `.env.example` was missing `NECTO_API_KEY`, even though the README documents it — added
   (commented out, so local dev stays open by default).
2. **HTTP retries were never implemented** although PLAN step ⑨ promised "buffer/batch/retry".
   `HttpTransport` now retries network/5xx failures (`attempts=2`, short backoff) but never retries 4xx,
   since a validation error cannot be fixed by retrying.
3. `Run.state_write` hard-coded `state:memory`; it now takes `state_id` (default `"memory"`).
4. `Necto()` with no endpoint still started a background flusher thread — now it only starts when
   something can actually be delivered.
5. SDK version was read via `__import__("necto_sdk").__version__`; moved to `_version.py` as the single
   source of truth, read by hatch at build time (`[tool.hatch.version]`).
6. Added the same ruff configuration to the SDK that the server uses.

### Not-a-bug (verified, worth recording)

- `X-Total-Count` **is** returned — an audit script checked it case-sensitively and was wrong.
- `framework` / `sdk_version` **are** stored from `meta` and from `run_start`; the create response only
  returns `id`, `status`, `schema_version` (by design).
- `score` events are accepted by the server even though SCHEMA marks them RESERVED for v2
  (deliberate leniency: forward-compatible, ignored by projection).

### Environment limitations (not code issues)

| Limit | Effect |
|---|---|
| `files.pythonhosted.org` blocked | `ruff` cannot be installed or added to dev deps; lint runs are
  unavailable locally until the network allows it |
| `github.com:443` blocked | `git push` must use `ssh.github.com:443` |
| Docker Hub DNS-poisoned | images pull via `docker.m.daocloud.io` (documented) |

---

## 15. Update log — Phase 3, step ⑬ (web app shell)

**Stack (per PLAN):** Vite 6 · React 19 · TypeScript 5.7 (strict) · Tailwind 4 · TanStack Query 5 ·
Zustand 5. Resolved versions: vite 6.4.6, react 19.3.1, @tanstack/react-query 5.107.1, zustand 5.1.0,
tailwindcss 4.3.5, typescript 5.7.3.

**What exists in `web/`:**

| File | Purpose |
|---|---|
| `vite.config.ts` | React + Tailwind plugins; proxy `/v1` (ws), `/healthz`, `/openapi.json` → :8000 |
| `src/lib/types.ts` | TypeScript mirrors of every server response schema |
| `src/lib/api.ts` | Typed fetch client; reads `X-Total-Count` for pagination totals |
| `src/lib/queries.ts` | TanStack Query hooks (health polls every 5 s, runs, global stats, topology) |
| `src/store/ui.ts` | Zustand store: active view, selected run, status filter |
| `src/components/*` | StatusPill, Metric, SummaryStrip, RecentRuns |
| `src/App.tsx` | App shell: sidebar nav + API status + summary metrics + runs table |

**Verified end-to-end (dev server against the live API):**

- `pnpm build` → tsc clean, 85 modules, `dist` 272 kB JS / 17.8 kB CSS
- HTML served with title + root div + React refresh
- `/healthz` proxied → `{status: ok, database: up, version: 0.1.0}`
- `/v1/runs`, `/v1/topology` (14 nodes), `/v1/stats` (11 runs / 67 events) proxied
- `POST /v1/runs` through the proxy works
- **WebSocket** `ws://localhost:5173/v1/live/runs/{id}` upgrades through Vite and returns `hello`

**Setup notes:**

- pnpm 12 blocks dependency build scripts; `web/.npmrc` allows `esbuild` via
  `only-built-dependencies[]=esbuild` (without this, Vite cannot start).
- Vite binds to `localhost` (IPv6-first on Windows) — use `http://localhost:5173`, not 127.0.0.1.
- `@types/node` is required for `process.env` in the Vite config.

**Next:** step ⑭ run detail + step ⑮ the interactive graph (@xyflow/react).

---

## 16. Update log — Phase 3, steps ⑭ + ⑮ (run detail + interactive graph)

**Step ⑭ — run detail.** Clicking a run opens `/` with `?run=<uuid>` (URL-synced, so a run is
linkable and survives reload). The page shows status, run id, `framework` (+ SDK version), events,
cost, tokens, errors, duration and relative start time.

**Step ⑮ — the interactive architecture graph** (`@xyflow/react` 12.12.1):

- Custom node per kind, colour-coded: agent (sky), model (violet), tool (amber), state (emerald),
  external (slate). Each node shows name, kind chip, event count, tokens, cost and error count.
- Edges styled per event type: handoff (sky, animated), llm_call (violet), tool_call/tool_result
  (amber), message (slate), state_write (emerald), error (rose), with arrowheads and labels
  (`kind ×count`).
- **Layout reads like the workflow**: agents form the left column in **handoff order** (found by
  walking handoff edges), and every model/tool/state node sits in its kind's column aligned to the
  row of the agent that first used it. Backward edges attach to opposite handles so they do not loop
  off-canvas.
- Dark-themed React Flow controls, background grid, fit-view with padding, legend below.

**Visual verification (new capability):** the UI was rendered with **headless Microsoft Edge**
(`msedge --headless=new --screenshot --window-size=1440,900 --virtual-time-budget=15s`) and the
PNGs were inspected. This caught four real defects that unit tests could never see:

1. React Flow's default **white controls strip** on the dark canvas → styled in `index.css`.
2. An **empty minimap box** overlapped by the attribution badge → minimap removed.
3. A dependency-depth layout **scattered the graph** (cycles pushed nodes apart) → replaced with the
   agent-column layout.
4. Agents were ordered **alphabetically** (researcher before router) → now ordered by handoff chain.

Screenshots committed to `docs/assets/graph-view.png` and `docs/assets/runs-view.png`.

**Build:** `pnpm build` → tsc clean, 113 modules, 474 kB JS / 37 kB CSS (150 kB / 7 kB gzip).

**Next:** step ⑯ live updates + replay scrubber, ⑰ inspector panel, ⑱ stats dashboard.

---

## 17. Update log — Phase 3, step ⑯ (live updates + replay)

**Live updates (`web/src/lib/ws.ts`).** `useLiveRun` opens `/v1/live/runs/{id}` (through the Vite
proxy, which handles the WebSocket upgrade). On `hello` it marks the connection live; on `events` it
invalidates the graph / events / run queries — so the graph, header metrics and timeline all refresh —
and it keeps the batch's edge ids for ~2.5 s so freshly-arrived edges render thicker and animated.
Reconnects automatically after a drop, and stops when the run finishes.

**Replay (`web/src/lib/projectGraph.ts` + `components/Timeline.tsx`).** The client re-implements the
server's graph projection (SCHEMA §7) so it can rebuild the graph from `events.slice(0, cursor)`.
A Live/Replay toggle plus a range slider scrubs through every event; the header shows
`N nodes · M edges · at event K`. `?run=<id>&at=<n>` deep-links straight into a replay position.

**Verified with a real browser (Edge over the DevTools Protocol):**

| Check | Result |
|---|---|
| WebSocket connected (live badge in UI) | ✅ |
| Post 2 events while the page is open | graph went **1 node → 3 nodes, 0 → 1 edges** |
| Time to update, no reload | **1.1 s** |
| Replay `?at=2` | **2 nodes · 0 edges · at event 2**, slider at 2/3 |

**Two bugs caught by looking at the rendered page:**

1. The replay cursor was stuck at the end: an effect that snapped the cursor to `total` in live mode
   ran after the deep-link effect and overwrote `setCursor(point)` in the same commit. Fixed by
   deriving the live cursor (`mode === "live" ? total : cursor`) instead of storing it.
2. Client-projected nodes rendered raw refs (`agent:researcher`, `model:openai:gpt-4o-mini`) because
   only `agent_start` set a name. Fixed by naming model/tool nodes from their payloads and falling
   back to the ref's last segment for inferred nodes.

Screenshots: `docs/assets/live-view.png`, `docs/assets/replay-view.png`.

**Next:** step ⑰ inspector panel (click node/edge → details), ⑱ stats dashboard.

---

## 18. Update log — Phase 3, step ⑰ (inspector). F4 done.

Clicking a node or an edge opens an inspector panel beside the graph:

- **Node** — id, kind, framework, model/provider, events, tokens, cost, errors, first/last seen,
  plus every event that mentions the node (`from_ref` or `to_ref`).
- **Edge** — kind, from/to labels, calls, tokens, cost, latency (a dash when the event type has none),
  error count/rate, first/last seen, plus the exact events that produced the edge.
- Each event row expands to its raw payload JSON.
- Selected elements get a sky-blue outline so the graph and the panel stay linked.
- The selection is URL-addressable (`?node=agent:router`, `?edge=...`), the panel closes on the ×
  or Escape, and it respects the replay position (events are filtered to the chosen point).

**Rerun found two real bugs:**

1. **Replay lost model-call cost on agents.** The client projection attributed an `llm_call`'s tokens
   and cost only to the model node, while the server attributes them to both ends. Replay showed
   `router: tokens 0 / $0` instead of `907 / $0.00210`. Fixed in `projectGraph.ts` (totals are summed
   from edges, so this does not double count).
2. **Stale per-run URL state.** Switching runs left `?at=`, `?node=` or `?edge=` behind, so opening
   another run could deep-link into a stale selection. Run navigation now clears those params.

Polish applied from the screenshots: selected-element outline, and `0 ms` latency replaced with a
dash for events that carry no latency (handoffs).

**Regression rerun:** server **64 passed**, SDK **51 passed, 1 skipped**, `pnpm build` clean
(118 modules, 487 kB JS / 154 kB gzip).

Screenshot: `docs/assets/inspector-view.png`.

**Next:** step ⑱ stats dashboard (Recharts), which completes Phase 3.

---

## 19. Update log — Phase 3, step ⑱ (stats dashboard). Phase 3 complete. F6 done.

`StatsView` (Recharts 3.10.1) with a run-scope selector (all runs ↔ one run):

| Panel | Content |
|---|---|
| Spend by model | total `cost_usd` per model |
| Model calls | calls per model (tokens on hover) |
| Calls by agent | horizontal bars per agent |
| Average LLM latency | avg ms per model |
| Events by type | donut of the event mix |
| Edge failure rate | edges with errors + rate bars |
| Busiest connections | topology table (scoped to the run when one is selected) |

Views are now URL-addressable: `?view=stats` (and `?run=<id>` scopes it).

**Rerun found two real bugs:**

1. **No bars rendered at all.** Recharts animates bars from zero height and the entry animation never
   completed under headless virtual time — every chart was empty while the axes looked fine. Fixed by
   `isAnimationActive={false}`; it also makes the dashboard paint instantly.
2. **Calls and tokens shared one Y axis**, so 12 calls rendered as a 1-pixel bar next to 3,400 tokens.
   Split into a calls-only chart (tokens now in the tooltip).

Also fixed: the edge panels ignored the run scope (they always showed global topology) and the first
metric duplicated "events" when scoped.

**Regression rerun:** server **64 passed**, SDK **51 passed, 1 skipped**, `pnpm build` clean
(recharts adds weight: 896 kB JS / 269 kB gzip — code-split the stats route before release).

### Phase 3 summary (steps ⑬–⑱) — DONE

| Step | Deliverable |
|---|---|
| ⑬ | Vite/React/Tailwind app shell, typed API client, proxy incl. WebSocket |
| ⑭ | Run detail: metrics, URL-addressable runs |
| ⑮ | Interactive architecture graph (React Flow): handoff-ordered layout, directional edges |
| ⑯ | Live WebSocket updates + replay scrubber with client-side projection |
| ⑰ | Inspector for nodes/edges with matching events and raw payloads |
| ⑱ | Stats dashboard: cost/tokens/latency per model & agent, event mix, edge failure rates |

**Next: Phase 4 — demo generator, first-boot seed, demo GIF, landing polish.**

---

## 20. Update log — Phase 4, step ⑲ (demo generator)

`scripts/demo.py` simulates a support-ticket pipeline and ships data through the **repo SDK**
(no dependencies; plain Python 3.10+):

- router classifies the ticket → researcher looks up policy (2 tools) → writer drafts the reply →
  critic reviews it. `state_write` stores the draft, `message` events carry the delegation.
- **Silent handoff failure**: the router's `message` contains the order id, but its `handoff`
  `context_snippet` does not — so nobody downstream has it. The critic raises an error at review
  time. Every third run is clean (`--clean` disables failures entirely).
- Flags: `--runs`, `--seed` (deterministic), `--delay` (pace events to watch the UI build live),
  `--endpoint`, `--api-key`.

**Verified:** 3 runs produced 23–24 events / 9 nodes / 13 edges each (4 agents, 2 models, 2 tools,
1 state node), costs around $0.012–0.015 per run, and the error correctly lands on the critic's
model-call edge in the two broken runs.

**Graph readability fix found by looking at the result:** edges carrying errors looked exactly like
healthy edges, so the whole point of the demo was invisible. Edges with `error_count > 0` are now
drawn in red with a `· N err` label, and the legend describes the overlay instead of a phantom
`error` edge kind.

**Code-splitting (carried over from step ⑱):** the stats route is now `React.lazy` + `Suspense`, so
Recharts is no longer on the critical path. Main bundle **896 kB → 490 kB** (154.8 kB gzip); the
stats chunk (406 kB / 114.8 kB gzip) loads only when opened.

Screenshot: `docs/assets/demo-run.png` (now the README hero).

**Next:** step ⑳ first-boot seed, then ㉑ demo GIF, ㉒ landing README.

---

## 21. Update log — Phase 4, step ⑳ (first-boot seed)

`NECTO_SEED=1` now fills an **empty** database with demo data on startup — the 30-second wow
with no manual step. Seeding runs inside the FastAPI lifespan, through the normal ingestion path
(`create_run` → `append_events` → `finish_run`), and only when the runs table is empty.

| File | Change |
|---|---|
| `server/necto_server/services/demo.py` | builds the support pipeline (same story as `scripts/demo.py`) and seeds it |
| `server/necto_server/config.py` | `seed` flag (`NECTO_SEED`) |
| `server/necto_server/main.py` | lifespan hook; seeding failures are logged and never block startup |
| `server/tests/test_seed.py` | 9 tests |

**Bug found by running it:** the flag did nothing at first. pydantic-settings maps a field named
`seed_demo` to `NECTO_SEED_DEMO`, while every doc said `NECTO_SEED`. Renamed the field to `seed`
and added a test that reads the env var, so the documented name is now the real one.

**Verified end-to-end on a fresh database:**

| Boot | Runs |
|---|---|
| first (`NECTO_SEED=1`, empty DB) | **6** (2 ok, 4 error — every third run clean) |
| second (`NECTO_SEED=1`, populated) | **6** — no duplicates |

Seeded totals: 142 events, $0.08, 16.2K tokens, 4 errors — the dashboard is populated on first
paint. Regression: server **74 passed**, SDK 51 passed.

Screenshot: `docs/assets/seed-view.png`.

**Next:** step ㉑ demo GIF, ㉒ landing README.

---

## 22. Update log — Phase 4, step ㉑ (demo GIF)

`scripts/demo_gif.py` renders `docs/assets/demo.gif` **without Playwright and without ffmpeg** —
neither is installed here and PyPI's file host is blocked. Instead:

1. it starts `scripts/demo.py --delay` so a run streams in live,
2. it drives the installed **Microsoft Edge** over the DevTools Protocol (a ~90-line stdlib
   WebSocket client — the only dependency is Pillow for GIF assembly),
3. it captures PNG frames while the graph builds, then a second segment with the run rewound and
   the **inspector open**,
4. it assembles a 6 fps, 720 px animated GIF with Pillow (1.17 MB, 31 frames, 720×607).

Usage: `python scripts/demo_gif.py` (server + `pnpm dev` must be running). Requires Edge and
Pillow; flags cover `--fps`, `--width`, `--event-delay`, `--live-seconds`, `--out`.

**Two real bugs found while making it:**

1. **`--delay` never streamed.** `scripts/demo.py` created the SDK with `background=False`, so
   events buffered until the run finished — the UI showed 0 events for the whole capture and then
   everything at once. It now enables the background flusher when a delay is set.
2. **The graph drifted off-canvas as it grew.** `fitView` only ran on mount, so new nodes landed
   outside the viewport. `GraphCanvas` now re-fits (220 ms animation) whenever the node/edge count
   changes — which also makes watching a live run much nicer.

Also: the first captures lost their opening seconds to Vite compiling the run-detail route; the
script now warms that route before starting the demo.

**Next:** step ㉒ landing README (badges, why-necto, quickstart polish).

---

## 23. Update log — Phase 4, step ㉒ (landing README). Phase 4 complete.

The README was rewritten as a landing page and its claims audited against reality:

- **Stale badge fixed**: it advertised 64 tests; the suites now total **125** (74 server + 51 SDK).
- Added a **"Why not just use a trace viewer?"** table positioning necto against LangSmith /
  Langfuse — and saying plainly where they are stronger (maturity, per-request depth).
- Added a "What it looks like" gallery (inspector, stats, live, replay) and the hero GIF.
- Condensed quickstart: DB → migrate → run API (`NECTO_SEED=1`) → run UI.
- Fixed a wrong command in the tests section (the SDK suite is run from the repo root with
  `PYTHONPATH=sdk`, not from `server/`).
- Every relative link and image was verified to resolve (scripted check).

**Phase 4 summary (steps ⑲–㉒) — DONE**

| Step | Deliverable |
|---|---|
| ⑲ | `scripts/demo.py` — support pipeline with a silent handoff failure; stats bundle split |
| ⑳ | `NECTO_SEED=1` first-boot seed (6 runs, idempotent) |
| ㉑ | `docs/assets/demo.gif` via Edge DevTools Protocol + Pillow |
| ㉒ | Landing README with badges, comparison, quickstart, gallery |

**Next: Phase 5 — CI (GitHub Actions), PyPI + GitHub release, community rails, launch.**

---

## 24. Polish pass — Tier 1 (pre-release manual-run fixes)

Audited the existing app for dead ends and unpolished edges, then fixed them in two batches.

**Batch 1 — bugs & dead ends**

| Fix | Before | After |
|---|---|---|
| Runs list auto-refresh | a running run stayed "running" until reload | polls every 5 s + invalidates on WebSocket events |
| Status filters | `statusFilter` existed in the store but no UI used it | All / Running / OK / Error chips, wired to `?status=`, URL-addressable |
| Replay metrics | header showed whole-run totals while the graph was at event K | header derives events/cost/tokens/errors from the projected graph, with an "at replay point" hint |
| Empty graph | a run with no events rendered a void | "No events yet" placeholder |
| Render errors | one exception blanked the app | `ErrorBoundary` with a reload path |

**Batch 2 — accessibility + topology**

- Global focus-visible rings, `aria-current` on nav, `aria-pressed` on filters/mode toggles,
  `aria-label` on the graph canvas, keyboard-reachable run links, and a
  `prefers-reduced-motion` override for animated edges.
- **Topology view implemented**: the aggregate map across all runs (nodes/edges/events/cost/errors),
  reusing `GraphCanvas`. The "soon" badge is gone.
- Themed scrollbars for the dark UI.

**Verified by screenshot:** filtered runs (2 of 2 error runs), replay at event 6 with matching header
totals (6 events / $0.00030 / 229 tokens), empty-run placeholder, and topology (17 nodes / 24 edges /
323 events across 27 runs).

**Next:** Tier 2 polish (pagination, search/sort, absolute timestamps, copy-JSON, edge tooltips,
favicon, responsive layout) and Tier 3 (Docker self-host, frontend tests, SDK 429 handling).

---

## 25. Examples for real-world testing

Added `examples/` so a first-time user can get real data in without reverse-engineering the SDK:

| Example | Needs | Shows |
|---|---|---|
| `examples/plain_sdk.py` | nothing | tracer API: agent, llm_call, handoff, tool round-trip |
| `examples/langgraph_app.py` | `langgraph` + `langchain-openai` + `OPENAI_API_KEY` | a real LangGraph graph, mapped automatically |
| `examples/openai_agents_app.py` | `openai-agents` + `OPENAI_API_KEY` | OpenAI Agents SDK with a real handoff |

`plain_sdk.py` was run end-to-end (8 events, framework `example`); the provider examples are
syntax-checked only — no API keys or provider packages are available on this machine.

Also: `NectoCallbackHandler.last_run_id` / `NectoProcessor.last_run_id` are now exposed, so an

---

## 26. Update log — network unblocked: lint, packaging and real-framework validation

The previously blocked hosts (`files.pythonhosted.org`, `github.com`, Docker Hub) are reachable
again. That unblocked four things that were explicitly deferred:

**1. Ruff is now a real dev dependency.** Added `ruff>=0.9` to `server/pyproject.toml`, refreshed
`uv.lock`, and added a root `ruff.toml` so `scripts/` and `examples/` share the same rules as the
two packages (they were being formatted with ruff's defaults). Fixed 21 findings + reformatted
~15 files. `ruff check` and `ruff format --check` are clean repo-wide.

**2. Pre-commit actually runs.** The ruff hooks are pinned to v0.17.4 and `pre-commit run
--all-files` passes. The prettier hook was removed: `pre-commit/mirrors-prettier` is archived and
its nodeenv bootstrap fails on this machine (frontend formatting is not enforced yet).

**3. The SDK has a real dev setup and its wheel is verified.** `sdk/uv.lock` + its own venv; `uv
build` produces a wheel that installs into a clean venv and records a run correctly. Tests jumped
to **52**.

**4. Real LangGraph integration test — and it found two shipping bugs:**

- `NectoCallbackHandler` was missing LangChain's `ignore_*` / `raise_error` / `run_inline`
  attributes. The first time a callback errored, LangChain's own error path raised
  `AttributeError: 'NectoCallbackHandler' object has no attribute 'raise_error'` and **the user's
  graph crashed**. Mock-based tests could never catch this.
- `otel.instrument()` imported opentelemetry even when the caller passed a `tracer_provider`, so an
  explicit provider failed with ImportError. Now only imports when it has to resolve the global
  provider.

`sdk/tests/test_langgraph_integration.py` runs a real `StateGraph` with a fake chat model and
asserts agents, handoffs and llm_calls (skipped unless `uv sync --group frameworks`).

**Also confirmed:** `docker pull hello-world` works straight from Docker Hub now (the
`docker.m.daocloud.io` mirror is no longer required, kept as a fallback in the docs), and
`git ls-remote https://github.com/...` succeeds — **the push blocker is gone**.

**Totals:** server **74 passed**, SDK **52 passed, 1 skipped**, lint/format clean, pre-commit green.
