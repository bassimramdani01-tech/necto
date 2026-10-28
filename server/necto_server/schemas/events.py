"""Wire schemas for the ingestion API — mirrors docs/SCHEMA.md (v1)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_EVENTS_PER_BATCH = 1000
MAX_EVENT_BYTES = 64 * 1024
MAX_SNIPPET_CHARS = 8192


class EventIn(BaseModel):
    """One event on the wire. Server overrides/normalises seq and run_id."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ts: datetime
    type: str
    schema_version: int
    from_ref: str | None = Field(default=None, alias="from")
    to_ref: str | None = Field(default=None, alias="to")
    payload: dict[str, Any] = Field(default_factory=dict)


class EventBatch(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=MAX_EVENTS_PER_BATCH)


# --------------------------------------------------------------------------
# Reference grammar and per-type reference rules (docs/SCHEMA.md §4 + §5).
# Enforced at ingestion so bad refs can never reach storage or the graph.
# --------------------------------------------------------------------------

ALLOWED_REF_KINDS = frozenset({"agent", "tool", "model", "external", "state"})

REF_PATTERN = re.compile(
    r"^(agent|tool|model|external|state):[A-Za-z0-9][A-Za-z0-9._:-]*$"
)

_AGENT = frozenset({"agent"})
_MODEL = frozenset({"model"})
_TOOL = frozenset({"tool"})
_STATE = frozenset({"state"})

# type -> (from_required, from_kinds, to_required, to_kinds)
# kinds=None means "any grammatically valid ref is acceptable".
REF_RULES: dict[str, tuple[bool, frozenset[str] | None, bool, frozenset[str] | None]] = {
    "run_start": (False, None, False, None),
    "run_finish": (False, None, False, None),
    "agent_start": (False, None, True, _AGENT),
    "agent_finish": (True, _AGENT, False, None),
    "llm_call": (True, _AGENT, True, _MODEL),
    "tool_call": (True, _AGENT, True, _TOOL),
    "tool_result": (True, _TOOL, True, _AGENT),
    "handoff": (True, _AGENT, True, _AGENT),
    "message": (True, _AGENT, True, _AGENT),
    "state_write": (True, _AGENT, True, _STATE),
    "error": (True, None, False, None),
}


def ref_kind(ref: str) -> str | None:
    """Return the kind prefix of a ref, or None when it has none."""
    kind, sep, _ = ref.partition(":")
    return kind if sep else None


def validate_refs(
    event_type: str, from_ref: str | None, to_ref: str | None
) -> list[str]:
    """Validate ref grammar plus per-type presence/kind rules.

    Returns a list of human-readable problems (empty means valid).
    """
    problems: list[str] = []
    grammar_ok = {"from": True, "to": True}

    for label, ref in (("from", from_ref), ("to", to_ref)):
        if ref is None:
            continue
        if not REF_PATTERN.match(ref):
            grammar_ok[label] = False
            problems.append(
                f"invalid '{label}' ref {ref!r}: expected 'kind:id' where kind is one of "
                f"{sorted(ALLOWED_REF_KINDS)} and id starts with a letter or digit"
            )

    rule = REF_RULES.get(event_type)
    if rule is None:
        return problems  # unknown type: grammar only, for forward compatibility

    from_required, from_kinds, to_required, to_kinds = rule
    if from_required and from_ref is None:
        problems.append(f"'{event_type}' requires a 'from' ref")
    if to_required and to_ref is None:
        problems.append(f"'{event_type}' requires a 'to' ref")
    if from_ref is not None and from_kinds is not None and grammar_ok["from"]:
        kind = ref_kind(from_ref)
        if kind not in from_kinds:
            problems.append(
                f"'{event_type}' 'from' must be one of {sorted(from_kinds)}, got {kind!r}"
            )
    if to_ref is not None and to_kinds is not None and grammar_ok["to"]:
        kind = ref_kind(to_ref)
        if kind not in to_kinds:
            problems.append(
                f"'{event_type}' 'to' must be one of {sorted(to_kinds)}, got {kind!r}"
            )

    return problems


# --------------------------------------------------------------------------
# Typed payloads. These validate known event types; storage keeps the raw
# payload verbatim so unknown/extra fields survive (see schema §2).
# --------------------------------------------------------------------------


class RunStartPayload(BaseModel):
    input: str
    meta: dict[str, Any] = Field(default_factory=dict)


class RunFinishPayload(BaseModel):
    status: Literal["ok", "error", "cancelled"]
    output: str | None = None
    duration_ms: int | None = None


class AgentStartPayload(BaseModel):
    name: str
    framework: str | None = None
    model: str | None = None
    input_snippet: str | None = None


class AgentFinishPayload(BaseModel):
    output_snippet: str | None = None
    duration_ms: int | None = None


class LLMCallPayload(BaseModel):
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    prompt_snippet: str | None = None
    response_snippet: str | None = None


class ToolCallPayload(BaseModel):
    name: str
    input_snippet: str | None = None


class ToolResultPayload(BaseModel):
    ok: bool
    latency_ms: int | None = None
    output_snippet: str | None = None


class HandoffPayload(BaseModel):
    reason: str | None = None
    context_snippet: str | None = None


class MessagePayload(BaseModel):
    content_snippet: str
    intent: str | None = None


class StateWritePayload(BaseModel):
    key: str
    value_snippet: str | None = None


class ErrorPayload(BaseModel):
    message: str
    stack: str | None = None
    recoverable: bool | None = None


class ScorePayload(BaseModel):
    name: str
    value: float


PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "run_start": RunStartPayload,
    "run_finish": RunFinishPayload,
    "agent_start": AgentStartPayload,
    "agent_finish": AgentFinishPayload,
    "llm_call": LLMCallPayload,
    "tool_call": ToolCallPayload,
    "tool_result": ToolResultPayload,
    "handoff": HandoffPayload,
    "message": MessagePayload,
    "state_write": StateWritePayload,
    "error": ErrorPayload,
    "score": ScorePayload,
}


class RunCreate(BaseModel):
    name: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1


class RunCreated(BaseModel):
    id: UUID
    status: str
    schema_version: int


class EventsAccepted(BaseModel):
    accepted: int
    last_seq: int


class RunFinishIn(BaseModel):
    status: Literal["ok", "error", "cancelled"] = "ok"
    output: str | None = None
    duration_ms: int | None = None


class RunFinished(BaseModel):
    id: UUID
    status: str
    finished: bool
