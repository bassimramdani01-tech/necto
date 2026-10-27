"""Wire schemas for the ingestion API — mirrors docs/SCHEMA.md (v1)."""

from __future__ import annotations

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
