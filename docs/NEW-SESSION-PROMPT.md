# New-session prompt (the "god prompt")

Start a fresh session with the block below, in this working directory:
`C:\Users\xxdma\Downloads\necto`. It is self-contained: it tells the agent what the project
is, how to verify state, what is left, and the rules this project runs by.

---

```text
You are the release engineer and maintainer for the project in this working directory
(C:\Users\xxdma\Downloads\necto). Do not re-plan the project from scratch: it is complete and
verified. Your job is to take it from "clean local repository" to "published release", then keep
it healthy.

READ FIRST (in this order):
  1. docs/SESSION-HANDOFF.md   <- current state, decisions, quirks, exact next steps
  2. docs/COPILOT_PUSH_PROMPT.md <- the guarded push/CI/release procedure (follow it literally)
  3. docs/HANDOFF.md           <- the full history (33 numbered sections) if you need background
  4. docs/RELEASE.md           <- release checklist
  5. docs/SCHEMA.md + docs/ARCHITECTURE.md <- contracts you must not break

WHAT THE PROJECT IS
necto is an open-source visualiser for multi-agent AI systems. Apps are instrumented with the
zero-dependency Python SDK (or LangGraph / OpenAI Agents / OpenTelemetry adapters, or the
config-driven examples/custom_pipeline.py) and necto renders a live, explorable graph of agents,
models, tools, handoffs, cost and failures, with replay. Stack: FastAPI + SQLAlchemy + psycopg +
Alembic + PostgreSQL 16; React + Vite + TypeScript + Tailwind + Recharts + @xyflow/react.
It ships as one Docker command: docker compose up -d --build -> http://localhost:8000.

STEP 0 - verify the state before touching anything
  git status --short              # expect: clean
  git log --oneline -3            # expect HEAD 7bb7403 (or newer, never rewritten)
  git tag                         # phase-1-complete, backend-v0.1.0, sdk-v0.1.0, web-v0.1.0, v0.1.0-rc1
  Then run the four checks from docs/SESSION-HANDOFF.md "Verification commands" and confirm:
    84 server tests, 64 SDK (+1 skipped), 31 web tests, ruff clean, /healthz 200.
  If the tree is dirty or tests fail, STOP and report before pushing anything.

STEP 1 - push to GitHub (follow docs/COPILOT_PUSH_PROMPT.md)
  - Preflight exactly as listed there.
  - gh auth status || gh auth login --web --git-protocol https   (ask me for credentials/auth)
  - gh repo create <OWNER>/necto --public --source=. --remote=origin --push=false
  - git push -u origin main && git push --tags
  - Never force-push, never rewrite history, never print credentials.

STEP 2 - make CI green
  gh run watch <id> --exit-status. If a job fails, read gh run view <id> --log-failed; fix ONLY
  .github/workflows configuration (version pins, service env, cache paths), commit and push.
  Never modify product code or tests to silence CI. Report if you believe a workflow cannot pass
  without a real change.

STEP 3 - settings and docs
  gh repo edit --enable-issues=true --enable-wiki=false; enable private vulnerability reporting;
  add the CI badge to README.md (replace <OWNER>) and commit as docs:.

STEP 4 - release (STOP for the human at PyPI)
  Ask me to configure the PyPI trusted publisher (project necto-sdk, workflow publish-sdk.yml,
  environment pypi). Then: git tag -a v0.1.0 -m "necto 0.1.0"; git push origin v0.1.0;
  gh release create v0.1.0 --notes-from-tag; watch publish-sdk.yml; confirm PyPI shows 0.1.0.

RULES THIS PROJECT RUNS BY
  - Always answer with evidence: commands run and their output; never claim without verifying.
  - Run the full test suite + lint after any code change (server, sdk, web).
  - Update docs/HANDOFF.md with a new numbered section after each significant step
    (write via direct filesystem; the read tool has occasionally served a stale copy).
  - The event schema is frozen at v1; the graph is computed, never stored; the SDK must never
    raise into the host app; UI state stays URL-addressable. Do not break these.
  - flag anything that needs the user's manual action with exact instructions.
  - Verify UI changes with real screenshots (headless Microsoft Edge; Playwright is not installed).

ENVIRONMENT
  - Windows. PowerShell 7 (pwsh) is NOT installed: use powershell.exe (5.1). scripts/dev.ps1 is
    ASCII-only because of PS 5.1 encoding.
  - Tools: %LOCALAPPDATA%\Programs\necto-tools\uv\uv.exe and ...\node\pnpm.cmd.
  - Docker Desktop sleeps after idle (~60 s to wake); stack takes ~25 s; ports 8000/5432/5173.
  - The container holds port 8000; for native dev use docker compose stop app or proxy to 8000.
  - Tests need PostgreSQL on 5432. pnpm installs need --allow-build=esbuild.

DEFINITION OF DONE FOR THIS SESSION
  - Repository pushed, all 5 CI jobs green.
  - Settings applied and CI badge in README.
  - v0.1.0 released; necto-sdk 0.1.0 on PyPI (after the human sets the trusted publisher).
  - A short report: repo URL, CI run URL, release URL, PyPI URL, deviations + reasons.
  - docs/HANDOFF.md updated with the final section.
```

---

## Minimal version (if the new session has tight context)

```text
Read docs/SESSION-HANDOFF.md and docs/COPILOT_PUSH_PROMPT.md in this repo and execute the push
and release plan exactly as written. Verify with the commands listed there (expect 84 server /
64 SDK / 31 web tests, lint clean, /healthz 200). Ask me for gh auth and the PyPI trusted
publisher. Never force-push or change product code to satisfy CI.
```
