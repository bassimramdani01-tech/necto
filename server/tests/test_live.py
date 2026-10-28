from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import WebSocketDisconnect


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _ev(type_: str, payload: dict, from_: str | None = None, to: str | None = None) -> dict:
    event: dict = {"ts": _ts(), "type": type_, "schema_version": 1, "payload": payload}
    if from_ is not None:
        event["from"] = from_
    if to is not None:
        event["to"] = to
    return event


def _create_run(client, name: str = "live-run") -> str:
    response = client.post("/v1/runs", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_live_hello_reports_current_state(client):
    run_id = _create_run(client)
    with client.websocket_connect(f"/v1/live/runs/{run_id}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["run_id"] == run_id
        assert hello["run_status"] == "running"
        assert hello["last_seq"] == 0


def test_live_pushes_new_events(client):
    run_id = _create_run(client)
    with client.websocket_connect(f"/v1/live/runs/{run_id}") as ws:
        assert ws.receive_json()["type"] == "hello"

        response = client.post(
            f"/v1/runs/{run_id}/events",
            json={
                "events": [_ev("handoff", {"reason": "research"}, from_="agent:a", to="agent:b")]
            },
        )
        assert response.status_code == 200, response.text

        message = ws.receive_json()
        assert message["type"] == "events"
        assert message["run_id"] == run_id
        assert len(message["events"]) == 1
        event = message["events"][0]
        assert event["seq"] == 1
        assert event["type"] == "handoff"
        assert event["from_ref"] == "agent:a"
        assert event["to_ref"] == "agent:b"


def test_live_pushes_a_whole_batch(client):
    run_id = _create_run(client)
    with client.websocket_connect(f"/v1/live/runs/{run_id}") as ws:
        assert ws.receive_json()["type"] == "hello"

        client.post(
            f"/v1/runs/{run_id}/events",
            json={
                "events": [
                    _ev("agent_start", {"name": "Planner"}, to="agent:planner"),
                    _ev(
                        "llm_call",
                        {"provider": "openai", "model": "gpt-4o-mini"},
                        from_="agent:planner",
                        to="model:openai:gpt-4o-mini",
                    ),
                ]
            },
        )

        message = ws.receive_json()
        assert message["type"] == "events"
        assert [e["seq"] for e in message["events"]] == [1, 2]


def test_live_reports_run_finished(client):
    run_id = _create_run(client)
    with client.websocket_connect(f"/v1/live/runs/{run_id}") as ws:
        assert ws.receive_json()["type"] == "hello"

        response = client.post(f"/v1/runs/{run_id}/finish", json={"status": "ok"})
        assert response.status_code == 200

        message = ws.receive_json()
        assert message["type"] == "run_finished"
        assert message["status"] == "ok"
        assert message["finished_at"] is not None


def test_live_hello_reflects_resumed_run(client):
    run_id = _create_run(client)
    client.post(
        f"/v1/runs/{run_id}/events",
        json={"events": [_ev("handoff", {}, from_="agent:a", to="agent:b")]},
    )

    with client.websocket_connect(f"/v1/live/runs/{run_id}") as ws:
        hello = ws.receive_json()
        assert hello["last_seq"] == 1


def test_live_unknown_run_is_closed(client):
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/v1/live/runs/{UUID(int=0)}") as ws,
    ):
        ws.receive_json()


def test_only_new_events_filters_duplicates():
    """Unit coverage for the connect-race dedupe helper (fix for lost events)."""
    from necto_server.api.live import _only_new_events

    message = {
        "type": "events",
        "run_id": "r",
        "events": [{"seq": 1}, {"seq": 2}, {"seq": 3}],
    }
    filtered = _only_new_events(message, last_seq=2)
    assert filtered is not None
    assert [event["seq"] for event in filtered["events"]] == [3]

    assert _only_new_events(message, last_seq=3) is None
    assert _only_new_events(message, last_seq=0) == message
    assert _only_new_events({"type": "run_finished", "status": "ok"}, last_seq=9) == {
        "type": "run_finished",
        "status": "ok",
    }
