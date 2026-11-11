"""First-boot demo data.

Set `NECTO_SEED=1` (or `NECTO_SEED=true`) to fill an *empty* database with a realistic
support-ticket pipeline on startup:

    router -> researcher -> writer -> critic

Every third run is clean; the others contain a **silent handoff failure** — the router drops the
order id when handing off, nobody notices, and the critic rejects the draft at review time. That is
the class of bug necto exists to make visible.

Seeding never duplicates: it only runs when the runs table is empty.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..schemas.events import EventBatch, EventIn, RunFinishIn
from . import ingestion, queries

logger = logging.getLogger(__name__)

DEMO_RUNS = 6

TICKETS = [
    ("#4471", "My order arrived damaged - can I get a refund?"),
    ("#5512", "I was charged twice for the same order."),
    ("#6120", "Cancelled my subscription but was still billed this month."),
    ("#7083", "The package never arrived and tracking says delivered."),
    ("#8234", "I received the wrong item and want an exchange."),
]

POLICIES = {
    "#4471": "Damaged goods: full refund within 30 days, no return required.",
    "#5512": "Duplicate charge: refund the duplicate once verified in the ledger.",
    "#6120": "Cancelled subscription billed again: refund plus confirmation email.",
    "#7083": "Missing package marked delivered: open a carrier claim before refunding.",
    "#8234": "Wrong item: exchange or refund, customer keeps the incorrect item.",
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(
    type_: str,
    payload: dict[str, Any],
    from_ref: str | None = None,
    to_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "ts": _ts(),
        "type": type_,
        "schema_version": 1,
        "from": from_ref,
        "to": to_ref,
        "payload": payload,
    }


def build_demo_events(
    index: int, rng: random.Random, clean: bool = False
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Build one run: (name, meta, events). Pure — no database or network access."""
    order_id, ticket = TICKETS[index % len(TICKETS)]
    policy = POLICIES[order_id]
    broken = (not clean) and (index % 3 != 0)

    events: list[dict[str, Any]] = [
        _event("run_start", {"input": ticket, "meta": {"order_id": order_id}}),
        # -- router --------------------------------------------------------
        _event("agent_start", {"name": "Router", "framework": "necto-demo"}, to_ref="agent:router"),
        _event(
            "llm_call",
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "input_tokens": rng.randint(180, 320),
                "output_tokens": rng.randint(20, 60),
                "latency_ms": rng.randint(240, 520),
                "cost_usd": round(rng.uniform(0.0002, 0.0006), 6),
                "prompt_snippet": f"Classify this support ticket: {ticket}",
            },
            "agent:router",
            "model:openai:gpt-4o-mini",
        ),
        _event(
            "message",
            {"content_snippet": f"Ticket {order_id}: {ticket}", "intent": "delegate"},
            "agent:router",
            "agent:researcher",
        ),
        # The failure: the message carried the order id, the handoff does not.
        _event(
            "handoff",
            {"reason": "needs refund policy", "context_snippet": "Ticket summary: damaged order refund request"},
            "agent:router",
            "agent:researcher",
        ),
        _event("agent_finish", {"duration_ms": rng.randint(700, 1400)}, from_ref="agent:router"),
        # -- researcher ----------------------------------------------------
        _event("agent_start", {"name": "Researcher", "framework": "necto-demo"}, to_ref="agent:researcher"),
        _event(
            "tool_call",
            {"name": "web_search", "input_snippet": f"refund policy {order_id}"},
            "agent:researcher",
            "tool:web_search",
        ),
        _event(
            "tool_result",
            {"ok": True, "latency_ms": rng.randint(320, 900), "output_snippet": policy[:80]},
            "tool:web_search",
            "agent:researcher",
        ),
        _event(
            "tool_call",
            {"name": "policy_db", "input_snippet": "lookup refund rules"},
            "agent:researcher",
            "tool:policy_db",
        ),
        _event(
            "tool_result",
            {"ok": True, "latency_ms": rng.randint(40, 120)},
            "tool:policy_db",
            "agent:researcher",
        ),
        _event(
            "llm_call",
            {
                "provider": "anthropic",
                "model": "claude-sonnet-4",
                "input_tokens": rng.randint(500, 900),
                "output_tokens": rng.randint(90, 180),
                "latency_ms": rng.randint(700, 1500),
                "cost_usd": round(rng.uniform(0.003, 0.009), 6),
                "response_snippet": policy[:100],
            },
            "agent:researcher",
            "model:anthropic:claude-sonnet-4",
        ),
        _event(
            "handoff",
            {"reason": "policy found", "context_snippet": policy[:120]},
            "agent:researcher",
            "agent:writer",
        ),
        _event("agent_finish", {"duration_ms": rng.randint(1800, 3200)}, from_ref="agent:researcher"),
        # -- writer --------------------------------------------------------
        _event("agent_start", {"name": "Writer", "framework": "necto-demo"}, to_ref="agent:writer"),
        _event(
            "state_write",
            {"key": "draft", "value_snippet": "Dear customer, regarding your order..."},
            "agent:writer",
            "state:memory",
        ),
        _event(
            "llm_call",
            {
                "provider": "anthropic",
                "model": "claude-sonnet-4",
                "input_tokens": rng.randint(600, 1100),
                "output_tokens": rng.randint(140, 260),
                "latency_ms": rng.randint(900, 1800),
                "cost_usd": round(rng.uniform(0.004, 0.011), 6),
                "response_snippet": "Dear customer, we are sorry about the damaged item...",
            },
            "agent:writer",
            "model:anthropic:claude-sonnet-4",
        ),
        _event("handoff", {"reason": "review draft"}, "agent:writer", "agent:critic"),
        _event("agent_finish", {"duration_ms": rng.randint(1600, 2800)}, from_ref="agent:writer"),
        # -- critic --------------------------------------------------------
        _event("agent_start", {"name": "Critic", "framework": "necto-demo"}, to_ref="agent:critic"),
        _event(
            "llm_call",
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "input_tokens": rng.randint(300, 600),
                "output_tokens": rng.randint(40, 120),
                "latency_ms": rng.randint(300, 700),
                "cost_usd": round(rng.uniform(0.0003, 0.0009), 6),
            },
            "agent:critic",
            "model:openai:gpt-4o-mini",
        ),
    ]

    if broken:
        events.append(
            _event(
                "error",
                {
                    "message": (
                        f"Reply references order {order_id}, but no handoff carried it; "
                        "the customer has to restate it"
                    ),
                    "recoverable": False,
                },
                from_ref="agent:critic",
            )
        )

    events.extend(
        [
            _event("agent_finish", {"duration_ms": rng.randint(800, 1600)}, from_ref="agent:critic"),
            _event(
                "run_finish",
                {
                    "status": "error" if broken else "ok",
                    "output": "draft sent back" if broken else "draft ready for review",
                },
            ),
        ]
    )

    name = f"support-ticket-{index + 1:03d}"
    meta = {
        "framework": "necto-demo",
        "sdk_version": "seed",
        "ticket": order_id,
        "channel": "email",
        "seeded": True,
    }
    return name, meta, events


def seed_demo_runs(
    db: Session, count: int = DEMO_RUNS, clean: bool = False, seed: int = 42
) -> list[str]:
    """Insert `count` demo runs through the normal ingestion path. Returns run ids."""
    run_ids: list[str] = []
    for index in range(count):
        rng = random.Random(seed + index)
        name, meta, events = build_demo_events(index, rng, clean=clean)
        run = ingestion.create_run(db, name, meta, 1)
        batch = EventBatch(events=[EventIn(**event) for event in events])
        ingestion.append_events(db, run.id, batch)
        status = "error" if any(event["type"] == "error" for event in events) else "ok"
        ingestion.finish_run(db, run.id, RunFinishIn(status=status, output="seeded demo run"))
        run_ids.append(str(run.id))
    return run_ids


def seed_if_empty(
    db: Session, count: int = DEMO_RUNS, clean: bool = False, seed: int = 42
) -> list[str]:
    """Seed only when there are no runs yet — safe to call on every boot."""
    if queries.count_runs(db, None) > 0:
        return []
    return seed_demo_runs(db, count=count, clean=clean, seed=seed)
