# Session handoff — necto

Written 2026-11-14 after the polish + Phase 5 work. **Read this first** in a new session; the
detailed history lives in [HANDOFF.md](HANDOFF.md) (33 numbered update sections) and the launch
steps in [COPILOT_PUSH_PROMPT.md](COPILOT_PUSH_PROMPT.md) / [RELEASE.md](RELEASE.md).

## TL;DR

necto is **complete and locally verified**: backend, Python SDK, web UI, Docker self-host, CI
workflows, release rails. The only thing left is the **GitHub push + first release**, which needs
the user's one-time credentials. Nothing is half-finished; the tree is clean.

| Fact | Value |
|---|---|
| Repository | `C:\Users\xxdma\Downloads\necto` |
| Branch | `main` |
| HEAD | `7bb7403` docs: update the Copilot push/release prompt … |
| Working tree | clean · 149 tracked files |
| Tags | `phase-1-complete`, `backend-v0.1.0`, `sdk-v0.1.0`, `web-v0.1.0`, `v0.1.0-rc1` |
| Tests | **84 server · 64 SDK (+1 skipped) · 31 web = 179** |
| Lint | ruff + pre-commit clean (76 Python files formatted) |
| Docker | `necto-app` + `necto-db` healthy during this session (`/healthz` 200, 7 runs in the dev DB). Docker Desktop sleeps after idle — run `docker compose up -d` first in the new session. |
| URLs | UI/API <http://localhost:8000> · dev UI <http://localhost:5173> |

## What necto is

An open-source visualiser for multi-agent AI systems: instrument an app (plain SDK, LangGraph,
OpenAI Agents, OpenTelemetry, or a config-defined pipeline), and see the live topology as a graph
— agents, models, tools, state, handoffs, cost, tokens, errors, replay.

Stack: FastAPI + SQLAlchemy 2 + psycopg3 + Alembic on PostgreSQL 16; zero-dependency Python SDK
with duck-typed framework adapters; React 19 + Vite 6 + TypeScript + Tailwind 4 + Recharts +
@xyflow/react, TanStack Query, Zustand.

## Architectural decisions (do not casually change)

1. **Event schema is frozen at v1** (`docs/SCHEMA.md`): 12 event types, envelope with
   `run_id/seq/ts/type/schema_version/from/to/payload`, refs are `kind:id`.
   Additive fields only; semantic changes need v2 + migration story.
2. **The graph is computed from events, never stored.** Replay, diff and topology are free because
   they project different event slices through `services/graph.py` / `lib/projectGraph.ts`.
3. **Server assigns `seq`** under `SELECT … FOR UPDATE`; batches are atomic.
4. **The SDK never raises into the host app**; transport failures are logged/dropped; background
   flushing + atexit flush; 429 honours `Retry-After`; 4xx (except 429) is not retried.
5. **UI state is URL-addressable**: `?run=`, `?at=` (replay cursor), `?node=`, `?edge=`,
   `?view=stats|topology`, `?status=`.
6. **Self-host = one command**: multi-stage Dockerfile (Node builds UI, python:3.12-slim runs API
   and serves `dist/` via `NECTO_WEB_DIR`), compose `db` + `app`, migrations at boot,
   `NECTO_SEED=1` seeds 6 demo runs on a fresh volume.
7. **Layering**: `api/` (HTTP) → `services/` (ingestion, graph, queries, demo, live hub) →
   `models.py`; no business logic in routes.

## What is done

| Area | State |
|---|---|
| Phase 1 backend | ingestion, graph, query, live WebSocket, auth (optional API key), migrations, 84 tests |
| Phase 2 SDK | tracer + LangGraph / OpenAI Agents / OpenTelemetry adapters, 64 tests incl. a real LangGraph StateGraph run |
| Phase 3 web UI | runs dashboard (search/filter/sort/pagination), graph, live, replay, inspector (copy JSON, replay-to-event), stats (lazy), topology, responsive shell, a11y focus styles, 31 vitest tests |
| Phase 4 demo | `scripts/demo.py` demo run, `NECTO_SEED`, `docs/assets/demo.gif`, landing README |
| Tier 1 polish | live-refreshing runs, status filters, replay-consistent metrics, empty graph state, error boundary |
| Tier 2 polish | search/sort/framework filters, load-more, timestamp tooltips, edge hover metrics, neighbour dimming, favicon/OG, mobile drawer |
| Tier 3 | Docker self-host, frontend tests, SDK hardening, dev scripts |
| Phase 5 rails | `ci.yml` (5 jobs), `publish-sdk.yml` (PyPI trusted publishing), dependabot, issue templates, CONTRIBUTING/SECURITY/CHANGELOG/RELEASE |
| Extras | stats hover-colour fix, config-driven "bring your own agents/models" pipeline (`examples/custom_pipeline.py`, `docs/BRING-YOUR-OWN.md`) |

## What remains (in order)

1. **Push to GitHub** — needs the user: `gh auth login` once, then
   `gh repo create <OWNER>/necto --public --source=. --remote=origin --push=false`,
   `git push -u origin main`, `git push --tags`.
   Full guarded procedure: `docs/COPILOT_PUSH_PROMPT.md`.
2. **First CI run green** — 5 jobs (server, sdk, web, lint, docker). Everything was validated
   locally under the same commands, but the workflow itself has never executed. Only fix CI
   configuration if something fails; never weaken tests.
3. **Repo settings** — enable issues, disable wiki, enable private vulnerability reporting,
   add the CI badge to README (replace `<OWNER>`).
4. **PyPI trusted publisher** — user action at <https://pypi.org/manage/account/publishing/>:
   project `necto-sdk`, workflow `publish-sdk.yml`, environment `pypi`.
5. **Release** — `git tag -a v0.1.0 -m "necto 0.1.0"`, push the tag, `gh release create`
   → `publish-sdk.yml` ships wheel + sdist.
6. Post-release ideas (not started): run retention/cleanup, CSV/JSON export, light theme,
   prettier enforcement for the web app, optional API-key management UI, multi-node live hub.

## Verification commands (copy-paste)

```powershell
cd C:\Users\xxdma\Downloads\necto
docker compose up -d                       # or the full stack: docker compose up -d --build
cd server; uv sync --frozen; uv run --no-sync alembic upgrade head; uv run --no-sync pytest -q; cd ..
cd sdk; uv sync --group frameworks; uv run pytest -q; cd ..
cd web; pnpm install --frozen-lockfile --allow-build=esbuild; pnpm test; pnpm build; cd ..
cd server; uv run ruff check .. ; uv run ruff format --check ..; cd ..
uvx ruff check .; uvx ruff format --check .
curl http://127.0.0.1:8000/healthz        # or Invoke-WebRequest
```

Expected: 84 passed · 64 passed, 1 skipped · 31 passed + built dist · lint clean · healthz 200.

## Environment notes and quirks (important)

- **Windows PowerShell 5.1 only** — `pwsh` (PowerShell 7) is **not installed**. Run
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -CheckOnly`.
  `scripts/dev.ps1` is deliberately **ASCII-only** (PS 5.1 reads BOM-less files as ANSI and
  breaks on em dashes).
- **Tool paths** (portable installs, not on PATH by default):
  `$env:LOCALAPPDATA\Programs\necto-tools\uv\uv.exe` and
  `$env:LOCALAPPDATA\Programs\necto-tools\node\pnpm.cmd`.
  `scripts/dev.ps1` resolves these or falls back to PATH.
- **Docker Desktop sleeps when idle** — starting the engine can take ~60 s; the stack then comes
  up in ~25 s. Ports: 8000 (app/UI), 5432 (db), 5173 (vite dev).
- **Port 8000 is held by the container.** For native dev either `docker compose stop app` or run
  uvicorn with `NECTO_API_TARGET=http://127.0.0.1:8000 pnpm dev` (vite proxies) on 5173.
- **pnpm 12 + `CI=true`** treats ignored build scripts as fatal; installs need
  `--allow-build=esbuild` (already in Dockerfile and CI).
- **Tests need PostgreSQL** on 5432; `tests/conftest.py` creates a `necto_test` database itself.
- **No Playwright/ffmpeg.** Screenshots/GIF are made with headless Microsoft Edge
  (`msedge --headless=new --screenshot=… --virtual-time-budget=…`) and CDP over a raw WebSocket;
  helper scripts live in `.tools/` (gitignored) — see "Loose ends".
- **Large docs/HANDOFF.md**: the file-reading tool occasionally returned a stale copy when
  rewriting it (silently dropping the newest section). Append via direct filesystem writes and
  verify with `grep`/PowerShell `Get-Content` afterwards.
- **Network**: PyPI, GitHub and Docker Hub are reachable now (earlier restrictions are gone);
  `git ls-remote https://github.com/…` succeeds.

## Repo map

```
server/            FastAPI app: api/, services/, schemas/, models.py, alembic/, tests/
sdk/               necto_sdk/: tracer, transport, events, adapters/{langgraph,openai_agents,otel}
web/               React app: src/views, src/components (graph/, Inspector, RecentRuns), lib/, store/
scripts/           demo.py, demo_gif.py, dev.ps1, reset.py, backfill_registries.py
examples/          plain_sdk.py, langgraph_app.py, openai_agents_app.py, custom_pipeline.py (+ json)
docs/              SCHEMA, ARCHITECTURE, DEVELOPMENT, HANDOFF, RELEASE, BRING-YOUR-OWN,
                   COPILOT_PUSH_PROMPT, SESSION-HANDOFF (this file), assets/
.github/           workflows/ci.yml, workflows/publish-sdk.yml, dependabot.yml, ISSUE_TEMPLATE/
```

## Loose ends / housekeeping

- `.tools/` (gitignored) holds ad-hoc QA scripts used during development: API/WS probes
  (`debug_probe.py`, `ws_debug.py`), the Edge-CDP hover/screenshot helper (`hover_shots.py`),
  YAML validation (`check_yaml.py`). They are not part of the product; recreate if needed.
- Screenshots used during QA are in `%TEMP%\necto-shots` (not committed). The README/GIF assets
  under `docs/assets/` **are** committed.
- The dev database currently has 7 runs (6 seeded demo runs + one `example-pipeline` recorded from
  the SDK example). Reset with `cd server && uv run python ../scripts/reset.py --yes --seed 6`.
- Nothing is uncommitted; no work product lives outside git except the ignored items above.

## If you only do one thing

Push the repository (step 1 above) and get CI green. Everything else in the roadmap is optional.
