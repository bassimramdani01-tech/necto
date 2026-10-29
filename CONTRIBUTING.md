# Contributing

The backend is complete; the Python SDK and web UI have not been built yet. Follow [the development setup](docs/DEVELOPMENT.md).

Run checks from `server/`: `uv run pytest -q`, `uv run ruff check .`, and `uv run ruff format --check .`. Pull requests need tests for their changes.

`docs/SCHEMA.md` is a frozen public contract. Breaking schema changes require a version bump.
