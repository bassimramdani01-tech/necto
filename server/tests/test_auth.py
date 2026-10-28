"""API-key authentication: disabled by default, enabled via NECTO_API_KEY."""

import pytest
from fastapi import WebSocketDisconnect

KEY = "test-secret-key"


def _enable(monkeypatch):
    from necto_server.config import settings

    monkeypatch.setattr(settings, "api_key", KEY)


def test_auth_disabled_by_default(client):
    assert client.get("/v1/runs").status_code == 200


def test_http_requires_key_when_configured(client, monkeypatch):
    _enable(monkeypatch)

    assert client.get("/v1/runs").status_code == 401
    assert client.get("/v1/runs", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/v1/runs", headers={"X-API-Key": KEY}).status_code == 200


def test_public_endpoints_stay_open(client, monkeypatch):
    _enable(monkeypatch)

    assert client.get("/").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_ingestion_requires_key(client, monkeypatch):
    _enable(monkeypatch)

    assert client.post("/v1/runs", json={"name": "denied"}).status_code == 401

    allowed = client.post("/v1/runs", json={"name": "allowed"}, headers={"X-API-Key": KEY})
    assert allowed.status_code == 201


def test_graph_and_stats_require_key(client, monkeypatch):
    _enable(monkeypatch)
    headers = {"X-API-Key": KEY}

    assert client.get("/v1/stats").status_code == 401
    assert client.get("/v1/stats", headers=headers).status_code == 200
    assert client.get("/v1/topology").status_code == 401
    assert client.get("/v1/topology", headers=headers).status_code == 200


def test_websocket_requires_key(client, monkeypatch):
    _enable(monkeypatch)
    headers = {"X-API-Key": KEY}

    run_id = client.post("/v1/runs", json={"name": "ws"}, headers=headers).json()["id"]

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/v1/live/runs/{run_id}") as ws,
    ):
        ws.receive_json()

    with client.websocket_connect(f"/v1/live/runs/{run_id}", headers=headers) as ws:
        assert ws.receive_json()["type"] == "hello"
