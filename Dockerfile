# ---------- build the web UI ----------
FROM node:25-alpine AS web
WORKDIR /web
ENV CI=true
RUN corepack enable && corepack prepare pnpm@12.11.2 --activate
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml web/.npmrc ./
RUN pnpm install --frozen-lockfile --allow-build=esbuild
COPY web/ ./
RUN pnpm build

# ---------- API + static UI ----------
FROM python:3.12-slim AS api
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# uv is only needed at build time to resolve the locked environment.
RUN pip install --no-cache-dir "uv==0.13.0"

COPY server/ ./
RUN uv sync --frozen --no-dev

COPY --from=web /web/dist ./web
ENV NECTO_WEB_DIR=/app/web
EXPOSE 8000

# Migrations are idempotent; running them at boot keeps "docker compose up" one step.
CMD ["sh", "-lc", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn necto_server.main:app --host 0.0.0.0 --port 8000"]