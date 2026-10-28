from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from necto_server.models import Event


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _ev(type_: str, payload: dict, from_: str | None = None, to: str | None = None) -> dict:
    event: dict = {"ts": _ts(), "type": type_, "schema_version": 1, "payload": payload}
    if from_ is not None:
        event["from"] = from_
    if to is not None:
        event["to"] = to
    return event


def _create_run(client, name: str = "q-run") -> str:
    response = client.post("/v1/runs", json={"name": name, "meta": {"framework": "pytest"}})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _post(client, run_id: str, events: list[dict]) -> None:
    response = client.post(f"/v1/runs/{run_id}/events", json={"events": events})
    assert response.status_code == 200, response.text


def _seed(client, name: str = "q-run") -> str:
    """7 events: tokens=2620, cost=0.0053, avg llm latency=1150."""
    run_id = _create_run(client, name)
    _post(
        client,
        run_id,
        [
            _ev("run_start", {"input": "go", "meta": {}}),
            _ev("agent_start", {"name": "Planner", "framework": "langgraph"}, to="agent:planner"),
            _ev(
                "llm_call",
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4",
                    "input_tokens": 800,
                    "output_tokens": 120,
                    "latency_ms": 1400,
                    "cost_usd": 0.0042,
                },
                from_="agent:planner",
                to="model:anthropic:claude-sonnet-4",
            ),
            _ev("handoff", {"reason": "sources"}, from_="agent:planner", to="agent:researcher"),
            _ev(
                "agent_start",
                {"name": "Researcher", "framework": "langgraph"},
                to="agent:researcher",
            ),
            _ev(
                "llm_call",
                {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "input_tokens": 1500,
                    "output_tokens": 200,
                    "latency_ms": 900,
                    "cost_usd": 0.0011,
                },
                from_="agent:researcher",
                to="model:openai:gpt-4o-mini",
            ),
            _ev("run_finish", {"status": "ok"}),
        ],
    )
    return run_id


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------


def test_list_runs_returns_summary(client):
    run_id = _seed(client)
    response = client.get("/v1/runs")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    run = runs[0]
    assert run["id"] == run_id
    assert run["event_count"] == 7
    assert run["tokens"] == 2620
    assert run["cost_usd"] == 0.0053
    assert run["error_count"] == 0


def test_list_runs_filters_by_status(client):
    running = _create_run(client, "still-running")
    finished = _seed(client, "finished")

    finish = client.post(f"/v1/runs/{finished}/finish", json={"status": "ok"})
    assert finish.status_code == 200

    ok_runs = client.get("/v1/runs", params={"status": "ok"}).json()
    assert [r["id"] for r in ok_runs] == [finished]

    running_runs = client.get("/v1/runs", params={"status": "running"}).json()
    assert [r["id"] for r in running_runs] == [running]


def test_list_runs_pagination(client):
    for i in range(3):
        _create_run(client, f"run-{i}")

    first_page = client.get("/v1/runs", params={"limit": 2}).json()
    assert len(first_page) == 2

    second_page = client.get("/v1/runs", params={"limit": 2, "offset": 2}).json()
    assert len(second_page) == 1

    first_ids = {r["id"] for r in first_page}
    second_ids = {r["id"] for r in second_page}
    assert len(first_ids) == 2
    assert len(second_ids) == 1
    assert not (first_ids & second_ids)


def test_get_run_detail(client):
    run_id = _seed(client, "detail-run")
    response = client.get(f"/v1/runs/{run_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "detail-run"
    assert body["meta"]["framework"] == "pytest"
    assert body["event_count"] == 7
    assert body["cost_usd"] == 0.0053


def test_get_run_404(client):
    response = client.get(f"/v1/runs/{UUID(int=0)}")
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------


def test_events_pagination(client):
    run_id = _seed(client)

    page1 = client.get(f"/v1/runs/{run_id}/events", params={"limit": 3}).json()
    assert [e["seq"] for e in page1["events"]] == [1, 2, 3]
    assert page1["has_more"] is True
    assert page1["next_after_seq"] == 3

    page2 = client.get(f"/v1/runs/{run_id}/events", params={"after_seq": 3, "limit": 3}).json()
    assert [e["seq"] for e in page2["events"]] == [4, 5, 6]
    assert page2["has_more"] is True

    page3 = client.get(f"/v1/runs/{run_id}/events", params={"after_seq": 6, "limit": 3}).json()
    assert [e["seq"] for e in page3["events"]] == [7]
    assert page3["has_more"] is False


def test_events_include_refs_and_payload(client):
    run_id = _seed(client)
    page = client.get(f"/v1/runs/{run_id}/events").json()
    handoff = next(e for e in page["events"] if e["type"] == "handoff")
    assert handoff["from_ref"] == "agent:planner"
    assert handoff["to_ref"] == "agent:researcher"
    assert handoff["payload"]["reason"] == "sources"


def test_events_404(client):
    response = client.get(f"/v1/runs/{UUID(int=0)}/events")
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------


def test_stats_aggregates_everything(client):
    _seed(client, "stats-a")
    _seed(client, "stats-b")

    response = client.get("/v1/stats")
    assert response.status_code == 200
    body = response.json()

    assert body["scope"] == "all"
    assert body["event_count"] == 14
    assert body["run_count"] == 2
    assert body["tokens"] == 5240
    assert body["cost_usd"] == 0.0106
    assert body["avg_llm_latency_ms"] == 1150.0
    assert body["by_type"]["llm_call"] == 4
    assert body["by_type"]["handoff"] == 2

    claude = next(m for m in body["by_model"] if m["model"] == "model:anthropic:claude-sonnet-4")
    assert claude["calls"] == 2
    assert claude["tokens"] == 1840
    assert claude["cost_usd"] == 0.0084

    planner = next(a for a in body["by_agent"] if a["agent"] == "agent:planner")
    assert planner["calls"] == 2
    assert planner["tokens"] == 1840


def test_stats_scoped_to_one_run(client):
    first = _seed(client, "scope-a")
    _seed(client, "scope-b")

    body = client.get("/v1/stats", params={"run_id": first}).json()
    assert body["scope"] == "run"
    assert body["run_id"] == first
    assert body["event_count"] == 7
    assert body["run_count"] == 1
    assert body["cost_usd"] == 0.0053


def test_stats_404_for_unknown_run(client):
    response = client.get("/v1/stats", params={"run_id": str(UUID(int=0))})
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Registries
# --------------------------------------------------------------------------


def test_agents_registry_is_populated(client):
    _seed(client)
    response = client.get("/v1/agents")
    assert response.status_code == 200
    agents = {a["ref"]: a for a in response.json()}
    assert set(agents) == {"agent:planner", "agent:researcher"}
    assert agents["agent:planner"]["name"] == "Planner"
    assert agents["agent:planner"]["framework"] == "langgraph"
    assert agents["agent:researcher"]["name"] == "Researcher"


def test_models_registry_is_populated(client):
    _seed(client)
    response = client.get("/v1/models")
    assert response.status_code == 200
    models = {m["ref"]: m for m in response.json()}
    assert set(models) == {
        "model:anthropic:claude-sonnet-4",
        "model:openai:gpt-4o-mini",
    }
    assert models["model:openai:gpt-4o-mini"]["provider"] == "openai"
    assert models["model:openai:gpt-4o-mini"]["name"] == "gpt-4o-mini"


def test_registry_is_not_duplicated_across_batches(client):
    run_id = _create_run(client, "two-batches")
    _post(
        client,
        run_id,
        [_ev("agent_start", {"name": "Writer", "framework": "langgraph"}, to="agent:writer")],
    )
    _post(
        client,
        run_id,
        [_ev("message", {"content_snippet": "hi"}, from_="agent:writer", to="agent:other")],
    )

    agents = client.get("/v1/agents").json()
    writer_entries = [a for a in agents if a["ref"] == "agent:writer"]
    assert len(writer_entries) == 1
    assert writer_entries[0]["name"] == "Writer"


# --------------------------------------------------------------------------
# Run metadata columns (regression: framework/sdk_version were never stored)
# --------------------------------------------------------------------------


def test_run_columns_populated_from_create_meta(client):
    response = client.post(
        "/v1/runs",
        json={
            "name": "meta-run",
            "meta": {"framework": "langgraph", "sdk_version": "0.1.0"},
        },
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    detail = client.get(f"/v1/runs/{run_id}").json()
    assert detail["framework"] == "langgraph"
    assert detail["sdk_version"] == "0.1.0"


def test_run_columns_backfilled_from_run_start_event(client):
    run_id = client.post("/v1/runs", json={"name": "no-meta"}).json()["id"]
    _post(
        client,
        run_id,
        [
            _ev(
                "run_start",
                {"input": "go", "meta": {"framework": "crewai", "sdk_version": "2.0.0"}},
            )
        ],
    )

    detail = client.get(f"/v1/runs/{run_id}").json()
    assert detail["framework"] == "crewai"
    assert detail["sdk_version"] == "2.0.0"
    assert detail["meta"]["framework"] == "crewai"


# --------------------------------------------------------------------------
# Stats resilience (regression: events without refs used to 500 /v1/stats)
# --------------------------------------------------------------------------


def test_stats_tolerates_legacy_events_without_refs(client, db):
    from necto_server.models import Run

    run_id = _create_run(client)
    run = db.execute(select(Run).where(Run.id == UUID(run_id))).scalars().one()
    db.add(
        Event(
            run_id=run.id,
            seq=1,
            ts=datetime.now(UTC),
            type="llm_call",
            from_ref=None,
            to_ref=None,
            payload={"provider": "openai", "model": "gpt-4o-mini", "cost_usd": 0.5},
        )
    )
    db.commit()

    response = client.get("/v1/stats")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["by_model"] == []
    assert body["by_agent"] == []
    assert body["event_count"] == 1


def test_run_list_reports_total_count(client):
    _seed(client, "count-a")
    _create_run(client, "count-b")

    response = client.get("/v1/runs", params={"limit": 1})
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"
    assert len(response.json()) == 1


def test_run_list_total_respects_status_filter(client):
    running = _create_run(client, "still-running")
    finished = _seed(client, "finished")
    client.post(f"/v1/runs/{finished}/finish", json={"status": "ok"})

    response = client.get("/v1/runs", params={"status": "running"})
    assert response.headers["X-Total-Count"] == "1"
    assert [run["id"] for run in response.json()] == [running]
