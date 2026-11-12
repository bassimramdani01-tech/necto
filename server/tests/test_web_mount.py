"""Serving the built web UI from the API (NECTO_WEB_DIR)."""

from fastapi.testclient import TestClient

from necto_server.config import settings
from necto_server.main import create_app


def _make_ui(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>necto ui</title>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('necto')", encoding="utf-8")
    return tmp_path


def test_web_ui_is_served_when_configured(tmp_path, monkeypatch):
    ui_root = _make_ui(tmp_path)
    monkeypatch.setattr(settings, "web_dir", str(ui_root))

    client = TestClient(create_app())

    index = client.get("/")
    assert index.status_code == 200
    assert "necto ui" in index.text
    assert client.get("/assets/app.js").status_code == 200
    # API endpoints keep working alongside the static mount.
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200


def test_api_root_stays_json_without_web_dir(monkeypatch):
    monkeypatch.setattr(settings, "web_dir", None)

    client = TestClient(create_app())

    body = client.get("/").json()
    assert body["name"] == "necto"
    assert body["health"] == "/healthz"
