"""Response schemas for the read/query surface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RunSummary(BaseModel):
    id: UUID
    name: str | None = None
    status: str
    schema_version: int
    framework: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    event_count: int = 0
    cost_usd: float = 0.0
    tokens: int = 0
    error_count: int = 0


class RunDetail(RunSummary):
    sdk_version: str | None = None
    meta: dict = Field(default_factory=dict)


class EventOut(BaseModel):
    seq: int
    ts: datetime
    type: str
    from_ref: str | None = None
    to_ref: str | None = None
    payload: dict = Field(default_factory=dict)


class EventsPage(BaseModel):
    run_id: UUID
    events: list[EventOut] = Field(default_factory=list)
    next_after_seq: int | None = None
    has_more: bool = False


class ByModel(BaseModel):
    model: str
    calls: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float | None = None


class ByAgent(BaseModel):
    agent: str
    calls: int = 0
    tokens: int = 0
    cost_usd: float = 0.0


class StatsResponse(BaseModel):
    scope: str
    run_id: UUID | None = None
    event_count: int = 0
    run_count: int = 0
    cost_usd: float = 0.0
    tokens: int = 0
    error_count: int = 0
    avg_llm_latency_ms: float | None = None
    by_type: dict[str, int] = Field(default_factory=dict)
    by_model: list[ByModel] = Field(default_factory=list)
    by_agent: list[ByAgent] = Field(default_factory=list)


class AgentOut(BaseModel):
    ref: str
    name: str | None = None
    kind: str
    framework: str | None = None
    first_seen: datetime
    last_seen: datetime


class ModelOut(BaseModel):
    ref: str
    provider: str | None = None
    name: str | None = None
    first_seen: datetime
    last_seen: datetime
