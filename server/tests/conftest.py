"""Test fixtures — the suite runs against an isolated 'necto_test' database."""

import os

import psycopg
import pytest
from sqlalchemy import text

_DEFAULT_URL = "postgresql+psycopg://necto:necto@127.0.0.1:5432/necto"
_TEST_DB = "necto_test"


def _head_and_name(url: str) -> tuple[str, str]:
    head, _, name = url.rpartition("/")
    return head, name


def _ensure_test_database() -> str:
    base_url = os.environ.get("NECTO_DATABASE_URL", _DEFAULT_URL)
    head, _ = _head_and_name(base_url)
    admin_dsn = head.replace("postgresql+psycopg://", "postgresql://") + "/postgres"
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute(
            "select 1 from pg_database where datname = %s", (_TEST_DB,)
        ).fetchone()
        if exists is None:
            conn.execute(f"CREATE DATABASE {_TEST_DB}")
    return head + "/" + _TEST_DB


# Must run before necto_server.config is imported anywhere.
os.environ["NECTO_DATABASE_URL"] = _ensure_test_database()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from necto_server.main import app

    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def test_schema():
    """Rebuild the test schema once per session so it always matches the models."""
    from necto_server import models  # noqa: F401  (register tables)
    from necto_server.db import Base, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clean_db(test_schema):
    from necto_server.db import engine

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE events, runs, agents, models RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture()
def db():
    from necto_server.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
