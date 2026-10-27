from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from necto_server.models import Event


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ev(type_: str, payload: dict, from_: str | None = None, to: str | None = None) -> dict:
    event: dict = {"ts": _ts(), "type": type_, "schema_version": 1, "payload": payload}
    if from_ is not None:
        event["from"] = from_
    if to is not None:
        event["to"] = to
    return event


def _create_run(client, name: str = "test-run") -> str:
    response = client.post("/v1/runs", json={"name": name, "meta": {"framework": "pytest"}})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_create_run_returns_uuid(client):
    response = client.post("/v1/runs", json={"name": "demo"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "running"
    UUID(body["id"])


def test_append_assigns_monotonic_sequence(client, db):
    run_id = _create_run(client)
    batch = {
        "events": [
            _ev("run_start", {"input": "hello", "meta": {}}),
            _ev(
                "handoff",
                {"reason": "needs_research"},
                from_="agent:router",
                to="agent:researcher",
            ),
        ]
    }
    response = client.post(f"/v1/runs/{run_id}/events", json=batch)
    assert response.status_code == 200, response.text
    assert response.json() == {"accepted": 2, "last_seq": 2}

    rows = (
        db.execute(select(Event).where(Event.run_id == run_id).order_by(Event.seq))
        .scalars()
        .all()
    )
    assert [row.seq for row in rows] == [1, 2]
    assert rows[1].from_ref == "agent:router"
    assert rows[1].to_ref == "agent:researcher"

    follow_up = client.post(
        f"/v1/runs/{run_id}/events",
        json={"events": [_ev("llm_call", {"provider": "openai", "model": "gpt-4o-mini"})]},
    )
    assert follow_up.status_code == 200
    assert follow_up.json() == {"accepted": 1, "last_seq": 3}


def test_unknown_event_type_is_accepted(client, db):
    run_id = _create_run(client)
    response = client.post(
        f"/v1/runs/{run_id}/events",
        json={"events": [_ev("future_kind", {"anything": 1})]},
    )
    assert response.status_code == 200, response.text
    row = db.execute(select(Event).where(Event.run_id == run_id)).scalars().one()
    assert row.type == "future_kind"


def test_invalid_payload_is_rejected(client):
    run_id = _create_run(client)
    response = client.post(
        f"/v1/runs/{run_id}/events",
        json={
            "events": [
                {
                    "ts": _ts(),
                    "type": "handoff",
                    "schema_version": 1,
                    "payload": {"reason": 12345},
                }
            ]
        },
    )
    assert response.status_code == 422


def test_unsupported_schema_version_is_rejected(client):
    run_id = _create_run(client)
    response = client.post(
        f"/v1/runs/{run_id}/events",
        json={
            "events": [
                {"ts": _ts(), "type": "handoff", "schema_version": 999, "payload": {}}
            ]
        },
    )
    assert response.status_code == 400


def test_append_to_missing_run_is_404(client):
    response = client.post(
        f"/v1/runs/{UUID(int=0)}/events", json={"events": [_ev("handoff", {})]}
    )
    assert response.status_code == 404


def test_finish_marks_run_and_blocks_further_events(client, db):
    run_id = _create_run(client)
    response = client.post(
        f"/v1/runs/{run_id}/finish", json={"status": "ok", "output": "done"}
    )
    assert response.status_code == 200
    assert response.json()["finished"] is True

    from necto_server.models import Run

    run = db.execute(select(Run).where(Run.id == run_id)).scalars().one()
    assert run.status == "ok"
    assert run.finished_at is not None
    assert run.meta["final_output"] == "done"

    blocked = client.post(
        f"/v1/runs/{run_id}/events", json={"events": [_ev("handoff", {})]}
    )
    assert blocked.status_code == 409


def test_snippets_are_truncated_to_8kb(client, db):
    run_id = _create_run(client)
    long_text = "x" * 20000
    response = client.post(
        f"/v1/runs/{run_id}/events",
        json={
            "events": [
                _ev(
                    "message",
                    {"content_snippet": long_text},
                    from_="agent:a",
                    to="agent:b",
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    row = db.execute(select(Event).where(Event.run_id == run_id)).scalars().one()
    assert len(row.payload["content_snippet"]) == 8192


def test_empty_batch_is_rejected(client):
    run_id = _create_run(client)
    response = client.post(f"/v1/runs/{run_id}/events", json={"events": []})
    assert response.status_code == 422
