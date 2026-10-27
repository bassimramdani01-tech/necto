from fastapi.testclient import TestClient

from necto_server.main import app

client = TestClient(app)


def test_root() -> None:
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "necto"
    assert body["version"] == "0.1.0"


def test_healthz_reports_database_up() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
