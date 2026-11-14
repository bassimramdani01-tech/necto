# Contributing to necto

Thanks for helping! necto is a small project, so a clear issue or a focused PR goes a long way.

## Setup

```bash
git clone <your-fork>
cd necto

# database
docker compose up -d db

# API (applies migrations, seeds demo runs on an empty DB)
cd server
uv sync
uv run alembic upgrade head
NECTO_SEED=1 uv run uvicorn necto_server.main:app --reload

# web UI (second terminal)
cd web
pnpm install
pnpm dev
```

Or use the one-command dev script (Windows PowerShell): `./scripts/dev.ps1`.

## Tests and lint

```bash
cd server && uv run pytest -q                 # 84 tests
cd sdk && uv run pytest -q                    # 61 tests (+1 skipped)
cd web && pnpm test                           # 31 tests
cd server && uv run ruff check .. && uv run ruff format --check ..
pre-commit run --all-files                    # same checks, on commit
```

## What to keep in mind

- **The event schema is frozen at v1.** Additive fields are fine; renames, removals or semantic
  changes need a new `schema_version` and a migration story in `docs/SCHEMA.md`.
- **Every new event type or payload rule needs tests** in `server/tests` — the schema is the
  contract everyone else builds on.
- **The SDK must never raise into the host app.** Transport failures are logged and dropped;
  keep it that way and add a regression test when touching `transport.py` or `tracer.py`.
- **The graph is computed, never stored.** Change `services/graph.py` rather than adding tables.
- **Web code is TypeScript strict**; the pure logic (projection, layout, formatting, store) has
  vitest tests — add one with any non-trivial behavior change.
- Prefer small PRs; include the command you ran and the output.

## Commit messages

Short imperative subject, optional scope prefix: `fix(server): ...`, `feat(sdk): ...`,
`docs: ...`, `test(web): ...`.
