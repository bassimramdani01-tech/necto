#!/usr/bin/env python3
"""Instrument the OpenAI Agents SDK — including a real handoff between agents.

Setup:
    pip install openai-agents
    export OPENAI_API_KEY=sk-...        # PowerShell: $env:OPENAI_API_KEY = "sk-..."

    python examples/openai_agents_app.py

The necto processor maps agent spans to agents, handoff spans to handoffs, generation spans
to llm_call (with tokens) and function spans to tool calls.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk"))

from agents import Agent, Runner, handoff  # noqa: E402

from necto_sdk import Necto  # noqa: E402
from necto_sdk.adapters.openai_agents import instrument  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--ui", default="http://localhost:5173")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--question", default="I was charged twice for order #5512")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    necto = Necto(endpoint=args.endpoint, api_key=args.api_key, framework="openai-agents")
    processor = instrument(necto, name="support-desk")

    billing = Agent(
        name="billing",
        model=args.model,
        instructions="Answer billing questions with a refund decision.",
    )
    triage = Agent(
        name="triage",
        model=args.model,
        instructions="Route the request to the right specialist.",
        handoffs=[handoff(billing)],
    )

    result = await Runner.run(triage, input=args.question)
    necto.close()

    print("answer:", str(result.final_output)[:200])
    print("run:", processor.last_run_id)
    print("open:", f"{args.ui}/?run={processor.last_run_id}")
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
