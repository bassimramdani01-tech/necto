from datetime import datetime, timezone

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


def _create_run(client, name: str = "graph-run") -> str:
    response = client.post("/v1/runs", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _post(client, run_id: str, events: list[dict]) -> None:
    response = client.post(f"/v1/runs/{run_id}/events", json={"events": events})
    assert response.status_code == 200, response.text


def _seed(client, name: str = "graph-run") -> str:
    run_id = _create_run(client, name)
    _post(
        client,
        run_id,
        [
            _ev("run_start", {"input": "go", "meta": {}}),
            _ev("agent_start", {"name": "Router", "framework": "langgraph"}, to="agent:router"),
            _ev(
                "llm_call",
                {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "latency_ms": 500,
                    "cost_usd": 0.001,
                },
                from_="agent:router",
                to="model:openai:gpt-4o-mini",
            ),
            _ev("handoff", {"reason": "research"}, from_="agent:router", to="agent:researcher"),
            _ev("agent_start", {"name": "Researcher", "framework": "langgraph"}, to="agent:researcher"),
            _ev("tool_call", {"name": "web_search"}, from_="agent:researcher", to="tool:web_search"),
            _ev("tool_result", {"ok": True, "latency_ms": 1200}, from_="tool:web_search", to="agent:researcher"),
            _ev(
                "llm_call",
                {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "input_tokens": 300,
                    "output_tokens": 50,
                    "latency_ms": 700,
                    "cost_usd": 0.002,
                },
                from_="agent:researcher",
                to="model:openai:gpt-4o-mini",
            ),
            _ev("run_finish", {"status": "ok"}),
        ],
    )
    return run_id


def test_run_graph_builds_nodes_and_edges(client):
    run_id = _seed(client)
    response = client.get(f"/v1/runs/{run_id}/graph")
    assert response.status_code == 200, response.text
    body = response.json()

    node_ids = {n["id"] for n in body["nodes"]}
    assert {
        "agent:router",
        "agent:researcher",
        "model:openai:gpt-4o-mini",
        "tool:web_search",
    } <= node_ids

    kinds = {n["id"]: n["kind"] for n in body["nodes"]}
    assert kinds["agent:router"] == "agent"
    assert kinds["model:openai:gpt-4o-mini"] == "model"
    assert kinds["tool:web_search"] == "tool"

    names = {n["id"]: n["name"] for n in body["nodes"]}
    assert names["agent:router"] == "Router"
    assert names["agent:researcher"] == "Researcher"
    assert names["model:openai:gpt-4o-mini"] == "gpt-4o-mini"

    assert body["stats"]["event_count"] == 9
    assert body["stats"]["cost_usd"] == 0.003
    assert body["stats"]["tokens"] == 470


def test_handoff_edge_is_marked_as_handoff(client):
    run_id = _seed(client)
    body = client.get(f"/v1/runs/{run_id}/graph").json()
    handoffs = [
        e
        for e in body["edges"]
        if e["kind"] == "handoff" and e["source"] == "agent:router" and e["target"] == "agent:researcher"
    ]
    assert len(handoffs) == 1
    assert handoffs[0]["count"] == 1


def test_llm_edge_accumulates_cost_and_tokens(client):
    run_id = _seed(client)
    body = client.get(f"/v1/runs/{run_id}/graph").json()
    edge = next(
        e
        for e in body["edges"]
        if e["kind"] == "llm_call" and e["source"] == "agent:researcher"
    )
    assert edge["count"] == 1
    assert edge["tokens"] == 350
    assert edge["cost_usd"] == 0.002
    assert edge["latency_ms"] == 700


def test_tool_result_edge_points_tool_to_agent(client):
    run_id = _seed(client)
    body = client.get(f"/v1/runs/{run_id}/graph").json()
    edge = next(e for e in body["edges"] if e["kind"] == "tool_result")
    assert edge["source"] == "tool:web_search"
    assert edge["target"] == "agent:researcher"
    assert edge["latency_ms"] == 1200


def test_empty_run_yields_empty_graph(client):
    run_id = _create_run(client, "empty")
    body = client.get(f"/v1/runs/{run_id}/graph").json()
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["stats"]["event_count"] == 0


def test_missing_run_graph_is_404(client):
    from uuid import UUID

    response = client.get(f"/v1/runs/{UUID(int=0)}/graph")
    assert response.status_code == 404


def test_topology_aggregates_across_runs(client):
    _seed(client, "run-a")
    _seed(client, "run-b")

    body = client.get("/v1/topology").json()
    assert body["run_id"] is None
    assert body["stats"]["run_count"] == 2

    handoff = next(
        e
        for e in body["edges"]
        if e["kind"] == "handoff" and e["source"] == "agent:router"
    )
    assert handoff["count"] == 2
    assert body["stats"]["cost_usd"] == 0.006


def test_error_is_attributed_to_last_edge(client, db):
    run_id = _create_run(client, "error-run")
    _post(
        client,
        run_id,
        [
            _ev("agent_start", {"name": "Writer"}, to="agent:writer"),
            _ev(
                "llm_call",
                {"provider": "openai", "model": "gpt-4o-mini", "cost_usd": 0.001},
                from_="agent:writer",
                to="model:openai:gpt-4o-mini",
            ),
            _ev("error", {"message": "rate limited", "recoverable": True}, from_="agent:writer"),
        ],
    )
    body = client.get(f"/v1/runs/{run_id}/graph").json()

    llm_edge = next(e for e in body["edges"] if e["kind"] == "llm_call")
    assert llm_edge["error_count"] == 1
    assert llm_edge["error_rate"] == 1.0

    writer = next(n for n in body["nodes"] if n["id"] == "agent:writer")
    assert writer["error_count"] == 1
