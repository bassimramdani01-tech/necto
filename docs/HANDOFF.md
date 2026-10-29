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
| Docker self-host | ⚠️ Partial | `docker-compose.yml` written, untested (Docker not installed on machine) |
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
$server = "$env:USERPROFILE\Downloads\necto\server"
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
- Run `docker compose up` once Docker is available.
- Phase 2 (SDK) and Phase 3 (web UI) are still unbuilt.
