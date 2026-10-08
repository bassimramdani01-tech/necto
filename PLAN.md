# necto — Step-by-Step Build Plan (MVP → GitHub)

Every step lists the exact tools. Dependencies marked **wait** must finish first.
Companion docs: [SPEC.md](SPEC.md) (vision) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (design)

---

## Phase 0 — Foundation

| # | Step | Tools / exact actions | Deliverable |
|---|---|---|---|
| 1 | **Detailed architecture** | This doc — all components, events, API, interactions, use cases | `docs/ARCHITECTURE.md` ✅ |
| 2 | **Freeze event schema v1** | Expand §4 of architecture into normative doc w/ JSON examples per type, graph projection rules, versioning policy | `docs/SCHEMA.md` |
| 3 | **Scaffold repo** | `git init` · LICENSE (MIT) · `.gitignore` (Python+Node+Docker) · `.editorconfig` · `.pre-commit-config.yaml` · README stub · issue/PR templates | repo skeleton |

## Phase 1 — Server & data core (wait: 2,3)

| # | Step | Tools / exact actions | Deliverable |
|---|---|---|---|
| 4 | Server skeleton | uv init · FastAPI + uvicorn · SQLAlchemy 2 + psycopg3 · Alembic · `docker compose up db` (`postgres:16-alpine`) · `GET /healthz` | `server/` boots |
| 5 | Ingestion API | Pydantic event models · `POST /v1/runs` · `/events` batch (seq in one tx) · `/finish` · pytest coverage | writes events |
| 6 | Graph projection | `services/graph.py`: events → nodes/edges, per-run + topology | `GET /graph`, `/topology` |
| 7 | Query API | runs list/detail · events w/ `after_seq` · stats rollups · agents/models registry | read surface |
| 8 | Live push | WebSocket `/v1/live/runs/{id}` + in-process pub/sub hub | live updates |

## Phase 2 — SDK (wait: 2,5)

| # | Step | Tools / exact actions | Deliverable |
|---|---|---|---|
| 9 | Core tracer | `necto-sdk` via uv · events.py · buffer/batch/retry · `transport/http.py` · never-crash policy | `pip install -e sdk` works |
| 10 | LangGraph adapter | callbacks → necto events | first real capture |
| 11 | OpenAI Agents adapter | trace hooks + handoff capture | handoffs visible |
| 12 | Generic/OTel path | manual JSON API docs + OTLP HTTP receiver | any-language escape hatch |

## Phase 3 — Web UI (wait: 6,7,8)

| # | Step | Tools / exact actions | Deliverable |
|---|---|---|---|
| 13 | App shell | pnpm + Vite 6 + React 19 + TS · Tailwind 4 · TanStack Query 5 · Zustand 5 · API client · Vite proxy → :8000 | `web/` serves |
| 14 | Runs view | run list + run detail skeleton | navigate runs |
| 15 | **Graph view** | **@xyflow/react 12**: custom nodes (agent/tool/model/external), weighted edges, minimap, controls, handoff styling | the core "wow" |
| 16 | Live + replay | WS client → animated edges · timeline scrubber rebuilding graph at time t | F2/F3 done |
| 17 | Inspector | click node/edge → event details, tokens, cost, raw JSON | F4 done |
| 18 | Stats dashboard | Recharts: cost/latency per agent/model, per-edge error rate | F6 done |

## Phase 4 — Demo & polish (wait: 8,15)

| # | Step | Tools / exact actions | Deliverable |
|---|---|---|---|
| 19 | Demo generator | `scripts/demo.py`: router→researcher→writer→critic run + intentional silent handoff failure | rich synthetic data |
| 20 | First-boot seed | `NECTO_SEED=1` on first boot | 30-second wow |
| 21 | **Demo GIF** | Playwright script → MP4 → ffmpeg → GIF · loop a live run + a debug moment | `assets/demo.gif` |
| 22 | Landing README | badges (shields.io) · GIF hero · quickstart · "why necto vs Langfuse" · architecture link | the pitch |

## Phase 5 — Publish & validate

| # | Step | Tools / exact actions | Deliverable |
|---|---|---|---|
| 23 | CI | GitHub Actions: ruff · pytest · tsc+eslint · docker build · (matrix) | green badge |
| 24 | Push + release | `git tag v0.1.0` · GitHub Releases · PyPI publish of `necto-sdk` via trusted publishing | public package |
| 25 | Community rails | CONTRIBUTING.md · issue templates · roadmap label | ready for issues |
| 26 | Launch | demo GIF post → r/LocalLLaMA, r/LangChain, Show HN, X | users + stars |

## Dev environment

- **Editors**: VS Code with: Python, Pylance, Ruff, Even Better TOML, ESLint, Prettier, Tailwind CSS IntelliSense, Docker, Playwright Test
- **Runtime deps**: Docker Desktop, uv, pnpm, Python 3.12, Node 20+
- **Daily loop**: `docker compose up db` · `uv run uvicorn` (reload) · `pnpm dev` (Vite proxy)
- **Self-host target**: `docker compose up` → everything at `http://localhost:8000`
