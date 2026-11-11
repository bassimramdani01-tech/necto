"""First-boot demo seed (NECTO_SEED=1)."""

import random
from uuid import UUID

from necto_server.config import Settings
from necto_server.schemas.events import EventBatch, EventIn
from necto_server.services import graph as graph_service
from necto_server.services import queries
from necto_server.services.demo import (
    build_demo_events,
    seed_demo_runs,
    seed_if_empty,
)


def test_seed_is_off_by_default():
    assert Settings.model_fields["seed"].default is False


def test_seed_env_var_is_read(monkeypatch):
    monkeypatch.setenv("NECTO_SEED", "1")
    assert Settings().seed is True


def test_demo_events_match_the_schema():
    _, _, events = build_demo_events(2, random.Random(1), clean=False)
    batch = EventBatch(events=[EventIn(**event) for event in events])
    assert len(batch.events) >= 20
    assert any(event.type == "error" for event in batch.events)


def test_clean_demo_runs_have_no_errors():
    _, _, events = build_demo_events(2, random.Random(1), clean=True)
    assert not any(event["type"] == "error" for event in events)


def test_demo_events_are_deterministic_for_a_seed():
    _, _, first = build_demo_events(0, random.Random(7), clean=False)
    _, _, second = build_demo_events(0, random.Random(7), clean=False)
    strip = lambda events: [  # noqa: E731 - tiny local helper
        {key: value for key, value in event.items() if key != "ts"} for event in events
    ]
    assert strip(first) == strip(second)


def test_seed_creates_runs_with_events(db):
    run_ids = seed_demo_runs(db, count=3)
    assert len(run_ids) == 3
    assert queries.count_runs(db, None) == 3

    detail = queries.get_run(db, UUID(run_ids[0]))
    assert detail is not None
    assert detail.event_count >= 20
    assert detail.framework == "necto-demo"


def test_seeded_graph_has_the_four_pipeline_agents(db):
    run_ids = seed_demo_runs(db, count=1)
    run_graph = graph_service.build_run_graph(db, UUID(run_ids[0]))
    agents = {node.id for node in run_graph.nodes if node.kind == "agent"}
    assert agents == {"agent:router", "agent:researcher", "agent:writer", "agent:critic"}


def test_seed_if_empty_fills_an_empty_database(db):
    assert seed_if_empty(db, count=2) != []
    assert queries.count_runs(db, None) == 2


def test_seed_if_empty_never_duplicates(db):
    seed_demo_runs(db, count=2)
    assert seed_if_empty(db, count=6) == []
    assert queries.count_runs(db, None) == 2


def test_some_seeded_runs_report_errors(db):
    seed_demo_runs(db, count=3)
    runs = queries.list_runs(db, status=None, limit=10, offset=0)
    statuses = sorted(run.status for run in runs)
    assert statuses == ["error", "error", "ok"]
