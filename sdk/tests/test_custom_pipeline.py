"""The bring-your-own-pipeline example records the config exactly as written."""

import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
sys.path.insert(0, str(EXAMPLES))

import custom_pipeline  # noqa: E402

from necto_sdk import Necto, RecordingTransport  # noqa: E402


def _config() -> dict:
    return custom_pipeline.load_config(EXAMPLES / "custom_pipeline.example.json")


def test_dry_run_records_the_configured_pipeline():
    transport = RecordingTransport()
    necto = Necto(transport=transport, background=False)
    run_id, replies = custom_pipeline.run_pipeline(_config(), necto, "help me", dry_run=True)
    necto.close()

    assert run_id
    assert len(replies) == 3

    events = transport.all_events()
    types = [event["type"] for event in events]
    assert types[0] == "run_start"
    assert types[-1] == "run_finish"
    assert types.count("agent_start") == 3
    assert types.count("llm_call") == 3
    assert types.count("handoff") == 2
    assert types.count("tool_call") == 1
    assert types.count("tool_result") == 1

    agents = {event["to"] for event in events if event["type"] == "agent_start"}
    assert agents == {"agent:triage", "agent:billing", "agent:writer"}
    models = {event["to"] for event in events if event["type"] == "llm_call"}
    assert models == {"model:openai:gpt-4o-mini", "model:anthropic:claude-sonnet-4"}


def test_unknown_model_reference_is_a_clear_error():
    config = _config()
    config["agents"][0]["model"] = "does-not-exist"
    necto = Necto(transport=RecordingTransport(), background=False)
    try:
        with pytest.raises(SystemExit):
            custom_pipeline.run_pipeline(config, necto, "x", dry_run=True)
    finally:
        necto.close()


def test_missing_key_gives_actionable_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(custom_pipeline.ProviderError) as info:
        custom_pipeline.call_model(
            {"provider": "openai", "model": "gpt-4o-mini"}, "hi", "", dry_run=False
        )
    assert "OPENAI_API_KEY" in str(info.value)
