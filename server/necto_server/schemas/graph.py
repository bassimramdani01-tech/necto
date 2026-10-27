"""Response schemas for graph projection (docs/SCHEMA.md §7)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    kind: str
    name: str | None = None
    framework: str | None = None
    model: str | None = None
    provider: str | None = None
    cost_usd: float = 0.0
    tokens: int = 0
    error_count: int = 0
    event_count: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str
    count: int = 0
    cost_usd: float = 0.0
    tokens: int = 0
    latency_ms: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    first_ts: datetime | None = None
    last_ts: datetime | None = None


class GraphStats(BaseModel):
    node_count: int = 0
    edge_count: int = 0
    event_count: int = 0
    run_count: int = 0
    cost_usd: float = 0.0
    tokens: int = 0
    error_count: int = 0


class GraphResponse(BaseModel):
    run_id: UUID | None = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    stats: GraphStats = Field(default_factory=GraphStats)
