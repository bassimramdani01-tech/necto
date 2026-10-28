"""SQL expressions for reading event metrics.

Metrics are extracted into typed columns at ingest (see models.Event), so these
helpers are plain column references — the read path never parses JSONB.
"""

from __future__ import annotations

from sqlalchemy import func

from ..models import Event


def cost_value():
    return Event.cost_usd


def tokens_value():
    return Event.tokens


def latency_value():
    return Event.latency_ms


def cost_sum():
    return func.coalesce(func.sum(Event.cost_usd), 0)


def tokens_sum():
    return func.coalesce(func.sum(Event.tokens), 0)
