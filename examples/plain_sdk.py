#!/usr/bin/env python3
"""Record a simulated multi-agent run with nothing but the necto SDK.

No model provider or API key needed — useful to check the wiring.

    python examples/plain_sdk.py
    python examples/plain_sdk.py --endpoint http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk"))

from necto_sdk import Necto  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--ui", default="http://localhost:5173")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    necto = Necto(endpoint=args.endpoint, api_key=args.api_key, framework="example")

    with necto.run(name="example-pipeline", meta={"language": "python"}) as run:
        run.agent_start("planner", name="Planner")
        run.llm_call(
            "planner", "openai", "gpt-4o-mini",
            input_tokens=120, output_tokens=40, cost_usd=0.0004, latency_ms=310,
            prompt_snippet="Plan the answer",
        )
        run.handoff("planner", "writer", reason="draft ready")

        run.agent_start("writer", name="Writer")
        run.tool_call("writer", "publish", input_snippet="draft")
        run.tool_result("publish", "writer", ok=True, latency_ms=90)
        run.agent_finish("writer", duration_ms=800)
        run.agent_finish("planner", duration_ms=1200)

    necto.close()
    print("run:", run.run_id)
    print("open:", f"{args.ui}/?run={run.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
