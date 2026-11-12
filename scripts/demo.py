#!/usr/bin/env python3
"""Generate realistic necto demo data.

Simulates a support-ticket pipeline: router -> researcher -> writer -> critic.
Every run except the clean ones contains a **silent handoff failure**: the router
drops the order id when handing off, nobody notices until the critic reviews the
draft, and the graph is what makes the missing context visible.

Usage:
    python scripts/demo.py                      # 3 runs against http://127.0.0.1:8000
    python scripts/demo.py --runs 8             # more data for the dashboard
    python scripts/demo.py --delay 0.4          # slow events so you can watch live
    python scripts/demo.py --endpoint http://host:8000 --api-key secret
    python scripts/demo.py --seed 7 --clean     # deterministic and failure-free
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk"))

from necto_sdk import Necto

DEFAULT_ENDPOINT = "http://127.0.0.1:8000"

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate necto demo runs.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="necto server base URL")
    parser.add_argument("--api-key", default=None, help="X-API-Key when the server requires one")
    parser.add_argument("--runs", type=int, default=3, help="how many runs to generate")
    parser.add_argument("--seed", type=int, default=42, help="random seed for repeatable data")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="seconds to sleep between events (use ~0.3-0.5 to watch the UI update live)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="do not inject the silent handoff failure (every run succeeds)",
    )
    return parser.parse_args()


class Emitter:
    """Tiny helper that emits an event and optionally sleeps."""

    def __init__(self, run, delay: float) -> None:
        self.run = run
        self.delay = delay

    def pause(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay)


def generate_run(
    necto: Necto, index: int, rng: random.Random, delay: float, clean: bool
) -> str | None:
    order_id, ticket = TICKETS[index % len(TICKETS)]
    policy = POLICIES[order_id]
    broken = (not clean) and (index % 3 != 0)

    with necto.run(
        name=f"support-ticket-{index + 1:03d}",
        meta={"framework": "necto-demo", "ticket": order_id, "channel": "email"},
    ) as run:
        emit = Emitter(run, delay)
        if run.disabled:
            return None

        run.run_start(input_text=ticket, meta={"order_id": order_id})
        emit.pause()

        # -- router: classify the ticket ---------------------------------
        run.agent_start("router", name="Router", framework="necto-demo", input_snippet=ticket)
        emit.pause()
        run.llm_call(
            "router",
            "openai",
            "gpt-4o-mini",
            input_tokens=rng.randint(180, 320),
            output_tokens=rng.randint(20, 60),
            latency_ms=rng.randint(240, 520),
            cost_usd=round(rng.uniform(0.0002, 0.0006), 6),
            prompt_snippet=f"Classify this support ticket: {ticket}",
        )
        emit.pause()

        run.message(
            "router",
            "researcher",
            content_snippet=f"Ticket {order_id}: {ticket}",
            intent="delegate",
        )
        emit.pause()

        # The failure: the delegate message carries the order id, the handoff does not.
        run.handoff(
            "router",
            "researcher",
            reason="needs refund policy",
            context_snippet="Ticket summary: damaged order refund request",
        )
        run.agent_finish("router", duration_ms=rng.randint(700, 1400))
        emit.pause()

        # -- researcher: look up policy ----------------------------------
        run.agent_start("researcher", name="Researcher", framework="necto-demo")
        emit.pause()
        run.tool_call(
            "researcher",
            "web_search",
            name="web_search",
            input_snippet=f"refund policy {order_id}",
        )
        emit.pause()
        run.tool_result(
            "web_search",
            "researcher",
            ok=True,
            latency_ms=rng.randint(320, 900),
            output_snippet=policy[:80],
        )
        emit.pause()
        run.tool_call(
            "researcher",
            "policy_db",
            name="policy_db",
            input_snippet="lookup refund rules",
        )
        emit.pause()
        run.tool_result("policy_db", "researcher", ok=True, latency_ms=rng.randint(40, 120))
        emit.pause()
        run.llm_call(
            "researcher",
            "anthropic",
            "claude-sonnet-4",
            input_tokens=rng.randint(500, 900),
            output_tokens=rng.randint(90, 180),
            latency_ms=rng.randint(700, 1500),
            cost_usd=round(rng.uniform(0.003, 0.009), 6),
            response_snippet=policy[:100],
        )
        emit.pause()
        run.handoff("researcher", "writer", reason="policy found", context_snippet=policy[:120])
        run.agent_finish("researcher", duration_ms=rng.randint(1800, 3200))
        emit.pause()

        # -- writer: draft the reply -------------------------------------
        run.agent_start("writer", name="Writer", framework="necto-demo")
        emit.pause()
        run.state_write("writer", "draft", value_snippet="Dear customer, regarding your order...")
        emit.pause()
        run.llm_call(
            "writer",
            "anthropic",
            "claude-sonnet-4",
            input_tokens=rng.randint(600, 1100),
            output_tokens=rng.randint(140, 260),
            latency_ms=rng.randint(900, 1800),
            cost_usd=round(rng.uniform(0.004, 0.011), 6),
            response_snippet="Dear customer, we are sorry about the damaged item...",
        )
        emit.pause()
        run.handoff("writer", "critic", reason="review draft")
        run.agent_finish("writer", duration_ms=rng.randint(1600, 2800))
        emit.pause()

        # -- critic: catch the silent failure ----------------------------
        run.agent_start("critic", name="Critic", framework="necto-demo")
        emit.pause()
        run.llm_call(
            "critic",
            "openai",
            "gpt-4o-mini",
            input_tokens=rng.randint(300, 600),
            output_tokens=rng.randint(40, 120),
            latency_ms=rng.randint(300, 700),
            cost_usd=round(rng.uniform(0.0003, 0.0009), 6),
        )
        emit.pause()

        if broken:
            run.error(
                "critic",
                f"Reply references order {order_id}, but no handoff carried it; "
                "the customer has to restate it",
                recoverable=False,
            )
            emit.pause()

        run.agent_finish("critic", duration_ms=rng.randint(800, 1600))
        run.run_finish(
            status="error" if broken else "ok",
            output="draft ready for review" if not broken else "draft sent back",
        )
        emit.pause()

        status = "error" if broken else "ok"
        run.finish(status=status)
        return run.run_id


def main() -> int:
    args = parse_args()
    # With --delay we want events to reach the server (and the UI) while the run is happening,
    # so let the tracer's background flusher ship each batch. Without a delay one flush at the
    # end is enough.
    necto = Necto(
        endpoint=args.endpoint,
        api_key=args.api_key,
        background=args.delay > 0,
        framework="necto-demo",
    )

    print(f"generating {args.runs} run(s) against {args.endpoint}")
    if args.delay > 0:
        print(f"  pacing: {args.delay}s between events (watch the UI live)")

    run_ids: list[str] = []
    for index in range(args.runs):
        rng = random.Random(args.seed + index)
        run_id = generate_run(necto, index, rng, args.delay, args.clean)
        if run_id is None:
            print("  ERROR: the server rejected the run - is it running and is the API key right?")
            necto.close()
            return 1
        run_ids.append(run_id)
        print(f"  run {index + 1}/{args.runs}: {run_id}")

    necto.close()
    print()
    print("done. open the UI at http://localhost:5173 and pick one:")
    for run_id in run_ids:
        print(f"  http://localhost:5173/?run={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
