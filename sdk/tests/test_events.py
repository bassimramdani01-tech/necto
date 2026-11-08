import pytest

from necto_sdk import events


def test_ref_builders():
    assert events.agent("router") == "agent:router"
    assert events.tool("web_search") == "tool:web_search"
    assert events.model("openai", "gpt-4o-mini") == "model:openai:gpt-4o-mini"
    assert events.external("user") == "external:user"
    assert events.state("memory") == "state:memory"


def test_ref_rejects_unknown_kind():
    with pytest.raises(ValueError):
        events.ref("sprite", "ghost")


def test_ref_rejects_empty_identifier():
    with pytest.raises(ValueError):
        events.agent("")


def test_event_envelope_matches_schema():
    ev = events.event("handoff", {"reason": "x"}, "agent:a", "agent:b")
    assert ev["type"] == "handoff"
    assert ev["schema_version"] == 1
    assert ev["from"] == "agent:a"
    assert ev["to"] == "agent:b"
    assert ev["payload"] == {"reason": "x"}
    assert ev["ts"].endswith("+00:00")
