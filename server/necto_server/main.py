from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import __version__
from .api.graph import router as graph_router
from .api.runs import router as ingestion_router
from .db import engine


def create_app() -> FastAPI:
    app = FastAPI(title="necto", version=__version__)
    app.include_router(ingestion_router)
    app.include_router(graph_router)

    @app.get("/")
    def root() -> dict:
        return {"name": "necto", "version": __version__, "docs": "/docs", "health": "/healthz"}

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

    return app


app = create_app()
