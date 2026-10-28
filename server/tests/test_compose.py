"""Guards the self-host compose file against configuration drift."""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def test_compose_exists():
    assert COMPOSE.is_file(), f"missing {COMPOSE}"


def test_compose_postgres_matches_app_defaults():
    config = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    db = config["services"]["db"]

    assert db["image"].startswith("postgres:16")

    env = db["environment"]
    assert env["POSTGRES_USER"] == "necto"
    assert env["POSTGRES_PASSWORD"] == "necto"
    assert env["POSTGRES_DB"] == "necto"

    from necto_server.config import Settings

    # Compare with the configured default, not the live setting (tests point it
    # at necto_test).
    default_url = Settings.model_fields["database_url"].default
    assert f"{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@" in default_url
    assert default_url.endswith(f"/{env['POSTGRES_DB']}")


def test_compose_exposes_postgres_port():
    config = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert "5432:5432" in config["services"]["db"]["ports"]
