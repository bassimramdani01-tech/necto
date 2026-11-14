#!/usr/bin/env python3
"""Bring your own agents and models: a config-driven pipeline recorded by necto.

Describe models, agents, tools and handoffs in JSON (or YAML), then run the pipeline. Every
step is recorded as necto events, so the resulting graph is your real architecture.

    python examples/custom_pipeline.py --dry-run                 # no API keys needed
    OPENAI_API_KEY=...    python examples/custom_pipeline.py      # real OpenAI calls
    ANTHROPIC_API_KEY=... python examples/custom_pipeline.py      # real Anthropic calls

Providers: openai (including any OpenAI-compatible base_url, e.g. Ollama/vLLM/OpenRouter),
anthropic, and mock (deterministic, for wiring tests).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "sdk") not in sys.path:
    sys.path.insert(0, str(ROOT / "sdk"))

from necto_sdk import Necto  # noqa: E402


class ProviderError(RuntimeError):
    """A model call failed; surfaced to the user, never raised from inside necto."""


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # optional dependency
        except ImportError as exc:
            raise SystemExit("YAML needs PyYAML: pip install pyyaml (or use JSON)") from exc
        config = yaml.safe_load(text)
    else:
        config = json.loads(text)
    if not isinstance(config, dict):
        raise SystemExit(f"{path} does not contain a config object")
    config.setdefault("name", "custom-pipeline")
    config.setdefault("framework", "custom")
    config["source"] = str(path)
    return config


def _post_json(url: str, body: dict, headers: dict, timeout: float = 60.0) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ProviderError(f"{url} -> HTTP {exc.code}: {detail}") from exc


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def call_model(spec: dict, prompt: str, system: str, dry_run: bool) -> dict:
    """Call one configured model and return reply + usage + cost + latency."""
    provider = spec.get("provider", "mock")
    model = spec.get("model", "mock-model")
    started = time.perf_counter()

    # Dry run keeps the real provider/model refs (so the graph shows the real architecture)
    # and only fakes the reply text — no network, no keys.
    if dry_run:
        reply = f"[dry-run:{provider}:{model}] {prompt[:100]}"
        input_tokens = _estimate_tokens(prompt)
        output_tokens = _estimate_tokens(reply)
    elif provider == "mock":
        reply = f"[mock:{model}] {prompt[:100]}"
        input_tokens = _estimate_tokens(prompt)
        output_tokens = _estimate_tokens(reply)
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is not set (use --dry-run to simulate)")
        base = spec.get("base_url", "https://api.openai.com/v1").rstrip("/")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        data = _post_json(
            f"{base}/chat/completions",
            {
                "model": model,
                "messages": messages,
                "temperature": spec.get("temperature", 0.2),
            },
            {"Authorization": f"Bearer {api_key}"},
        )
        reply = str(data["choices"][0]["message"]["content"])
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or _estimate_tokens(prompt))
        output_tokens = int(usage.get("completion_tokens") or _estimate_tokens(reply))
    elif provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set (use --dry-run to simulate)")
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": spec.get("max_tokens", 512),
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            body,
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        reply = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or _estimate_tokens(prompt))
        output_tokens = int(usage.get("output_tokens") or _estimate_tokens(reply))
    else:
        raise ProviderError(f"unknown provider {provider!r} (use openai, anthropic or mock)")

    latency_ms = int((time.perf_counter() - started) * 1000)
    rates = spec.get("rates") or {}
    cost_usd = (
        input_tokens / 1000 * float(rates.get("input_per_1k", 0))
        + output_tokens / 1000 * float(rates.get("output_per_1k", 0))
    )
    return {
        "provider": provider,
        "model": model,
        "reply": reply,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
    }


def run_pipeline(config: dict, necto: Necto, prompt: str, dry_run: bool) -> tuple[str | None, list[str]]:
    """Execute the configured flow, recording each step through the tracer."""
    models = config.get("models") or {}
    tools = config.get("tools") or {}
    agents = {agent["id"]: agent for agent in config.get("agents", [])}
    flow = config.get("flow") or list(agents)
    if not flow:
        raise SystemExit("config has no agents/flow")

    replies: list[str] = []
    meta = {"framework": config["framework"], "config": config["source"]}
    with necto.run(name=config["name"], meta=meta) as run:
        run.run_start(prompt, meta={"pipeline": config["name"]})
        previous: str | None = None
        current = prompt
        for agent_id in flow:
            agent = agents[agent_id]
            spec = models.get(agent.get("model", "default"))
            if spec is None:
                raise SystemExit(f"agent {agent_id!r} references an unknown model")
            if previous is not None:
                run.handoff(previous, agent_id, reason=agent.get("handoff_reason", "next step"))
            run.agent_start(
                agent_id,
                name=agent.get("name", agent_id),
                framework=config["framework"],
                model=spec.get("model"),
                input_snippet=current[:120],
            )

            result = call_model(spec, current, agent.get("system", ""), dry_run)
            run.llm_call(
                agent_id,
                result["provider"],
                result["model"],
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_usd=result["cost_usd"],
                latency_ms=result["latency_ms"],
                prompt_snippet=current[:120],
                response_snippet=result["reply"][:120],
            )

            reply = result["reply"]
            for tool_id in agent.get("tools", []):
                tool = tools.get(tool_id, {})
                run.tool_call(agent_id, tool_id, name=tool.get("name", tool_id), input_snippet=current[:80])
                tool_reply = tool.get("reply", "(no reply configured)")
                run.tool_result(tool_id, agent_id, ok=True, latency_ms=40, output_snippet=str(tool_reply)[:120])
                reply = f"{reply}\n[{tool_id}] {tool_reply}"

            run.agent_finish(agent_id, output_snippet=reply[:160])
            replies.append(reply)
            previous = agent_id
            current = reply
        run.run_finish("ok", output=replies[-1][:200] if replies else None)

    return run.run_id, replies


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(Path(__file__).with_name("custom_pipeline.example.json")))
    parser.add_argument("--prompt", default="Customer says they were charged twice for order #5512. Resolve it.")
    parser.add_argument("--endpoint", default=os.environ.get("NECTO_ENDPOINT", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.environ.get("NECTO_API_KEY"))
    parser.add_argument("--dry-run", action="store_true", help="simulate replies; no API keys needed")
    parser.add_argument("--ui", default=os.environ.get("NECTO_UI", "http://localhost:5173"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))
    necto = Necto(endpoint=args.endpoint, api_key=args.api_key, framework=config["framework"])
    try:
        run_id, replies = run_pipeline(config, necto, args.prompt, args.dry_run)
    finally:
        necto.close()
    for index, reply in enumerate(replies, start=1):
        print(f"[{index}/{len(replies)}] {reply[:160]}")
    print("run:", run_id)
    print("open:", f"{args.ui}/?run={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())