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


# --------------------------------------------------------------------------
# Topology is now aggregated in SQL — these lock in parity and correctness.
# --------------------------------------------------------------------------


def test_topology_agrees_with_in_memory_projection(client, db):
    """The SQL topology must match the Python projection used for run graphs."""
    _seed(client, "parity-a")
    _seed(client, "parity-b")

    from necto_server.services import graph

    events = (
        db.execute(select(Event).order_by(Event.run_id, Event.seq)).scalars().all()
    )
    nodes, edges, _totals = graph.project(list(events))
    expected_nodes, expected_edges = graph._finalize(nodes, edges)

    actual = client.get("/v1/topology").json()

    def node_view(node) -> tuple:
        return (
            node["id"],
            node["kind"],
            node["name"],
            node["event_count"],
            round(float(node["cost_usd"]), 8),
            node["tokens"],
            node["error_count"],
        )

    def edge_view(edge) -> tuple:
        return (
            edge["source"],
            edge["target"],
            edge["kind"],
            edge["count"],
            round(float(edge["cost_usd"]), 8),
            edge["tokens"],
            edge["latency_ms"],
            edge["error_count"],
            edge["error_rate"],
        )

    assert sorted(node_view(n.model_dump()) for n in expected_nodes) == sorted(
        node_view(n) for n in actual["nodes"]
    )
    assert sorted(edge_view(e.model_dump()) for e in expected_edges) == sorted(
        edge_view(e) for e in actual["edges"]
    )
    assert actual["stats"]["event_count"] == 18
    assert actual["stats"]["run_count"] == 2


def test_topology_keeps_node_names(client):
    _seed(client, "names")
    body = client.get("/v1/topology").json()
    names = {node["id"]: node["name"] for node in body["nodes"]}
    assert names["agent:router"] == "Router"
    assert names["agent:researcher"] == "Researcher"
    assert names["model:openai:gpt-4o-mini"] == "gpt-4o-mini"
    assert names["tool:web_search"] == "web_search"


def test_topology_error_attribution_is_per_run(client):
    """An error must attach to its own run's last edge, never another run's."""
    run_a = _create_run(client, "err-a")
    _post(
        client,
        run_a,
        [
            _ev("handoff", {"reason": "x"}, from_="agent:a", to="agent:b"),
            _ev("error", {"message": "boom"}, from_="agent:a"),
        ],
    )

    run_b = _create_run(client, "err-b")
    _post(client, run_b, [_ev("error", {"message": "boom2"}, from_="agent:a")])

    body = client.get("/v1/topology").json()
    handoff = next(e for e in body["edges"] if e["kind"] == "handoff")
    assert handoff["count"] == 1
    # only run A's error is attributable; run B has no edge before its error
    assert handoff["error_count"] == 1
    assert handoff["error_rate"] == 1.0


def test_topology_error_attaches_to_the_most_recent_edge(client):
    run_id = _create_run(client, "two-edges")
    _post(
        client,
        run_id,
        [
            _ev("handoff", {"reason": "one"}, from_="agent:a", to="agent:b"),
            _ev("handoff", {"reason": "two"}, from_="agent:a", to="agent:c"),
            _ev("error", {"message": "boom"}, from_="agent:a"),
        ],
    )

    body = client.get("/v1/topology").json()
    a_to_b = next(
        e for e in body["edges"] if e["source"] == "agent:a" and e["target"] == "agent:b"
    )
    a_to_c = next(
        e for e in body["edges"] if e["source"] == "agent:a" and e["target"] == "agent:c"
    )
    assert a_to_b["error_count"] == 0
    assert a_to_c["error_count"] == 1
