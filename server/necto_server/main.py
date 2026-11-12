import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import __version__
from .api.graph import router as graph_router
from .api.live import router as live_router
from .api.query import router as query_router
from .api.runs import router as ingestion_router
from .config import settings
from .db import SessionLocal, engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Optionally fill an empty database with demo runs on first boot (NECTO_SEED=1)."""
    if settings.seed:
        try:
            from .services.demo import seed_if_empty  # imported lazily: keeps boot light

            with SessionLocal() as db:
                seeded = seed_if_empty(db)
            if seeded:
                logger.info("seeded %s demo runs (NECTO_SEED)", len(seeded))
            else:
                logger.info("NECTO_SEED is on but the database already has runs; not seeding")
        except Exception:  # noqa: BLE001 - never block startup on demo data
            logger.warning("demo seeding failed; continuing without demo data", exc_info=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="necto", version=__version__, lifespan=lifespan)
    app.include_router(ingestion_router)
    app.include_router(graph_router)
    app.include_router(live_router)
    app.include_router(query_router)

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        database = "up"
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            database = "down"

        status = "ok" if database == "up" else "degraded"
        return JSONResponse(
            status_code=200 if database == "up" else 503,
            content={"status": status, "database": database, "version": __version__},
        )

    # Self-host: serve the built web UI from the API when NECTO_WEB_DIR is set.
    web_root = Path(settings.web_dir) if settings.web_dir else None
    if web_root is not None and web_root.is_dir():
        app.mount("/", StaticFiles(directory=str(web_root), html=True), name="web")
    else:

        @app.get("/")
        def root() -> dict:
            return {
                "name": "necto",
                "version": __version__,
                "docs": "/docs",
                "health": "/healthz",
            }

    return app


app = create_app()
