"""LangGraph / LangChain integration.

LangGraph uses the LangChain callback system, so one handler covers both.

Usage:

    from necto_sdk import Necto
    from necto_sdk.adapters.langgraph import NectoCallbackHandler

    necto = Necto(endpoint="http://127.0.0.1:8000", framework="langgraph")
    handler = NectoCallbackHandler(necto)

    result = graph.invoke(inputs, config={"callbacks": [handler]})

Mapping:

| LangChain callback        | necto event                |
|---------------------------|----------------------------|
| root `on_chain_start`     | creates the run            |
| `on_chain_start` (node)   | `agent_start`              |
| node → node transition    | `handoff`                  |
| `on_chat_model_start/end` | `llm_call` (tokens, ms)    |
| `on_tool_start/end`       | `tool_call` / `tool_result` |
| `*_error`                 | `error`                    |
| root `on_chain_end`       | finishes the run           |

Handoffs are inferred from node-to-node transitions: LangGraph executes nodes in
sequence, so a change of node is a change of control. This is a heuristic; nested
subgraphs may produce extra transitions.

This module does not import langchain or langgraph — it works with plain objects
that expose the same callback signatures.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any

from ..tracer import Necto, Run

logger = logging.getLogger(__name__)


def _guard(method):
    """Callbacks must never raise into the framework."""

    @functools.wraps(method)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return method(self, *args, **kwargs)
        except Exception:  # noqa: BLE001 - never break the user's graph
            logger.warning("necto: langgraph adapter failed in %s", method.__name__, exc_info=True)
            return None

    return wrapper


def _node_name(
    metadata: dict[str, Any] | None, serialized: Any, kwargs: dict[str, Any]
) -> str | None:
    """Best-effort name of the graph node a callback belongs to."""
    if isinstance(metadata, dict):
        node = metadata.get("langgraph_node")
        if node:
            return str(node)
    name = kwargs.get("name")
    if name:
        return str(name)
    if isinstance(serialized, dict):
        for key in ("name", "id"):
            if serialized.get(key):
                return str(serialized[key])
    return None


def _model_name(serialized: Any, kwargs: dict[str, Any]) -> tuple[str, str]:
    """Return (provider, model) from a serialized runnable, best effort."""
    provider = "unknown"
    model = "unknown"
    if isinstance(serialized, dict):
        for key in ("model_name", "model"):
            value = serialized.get(key)
            if value:
                model = str(value)
                break
        else:
            nested = serialized.get("kwargs")
            if isinstance(nested, dict):
                for key in ("model_name", "model"):
                    if nested.get(key):
                        model = str(nested[key])
                        break
        model_class = str(serialized.get("name") or "")
        lowered = model_class.lower()
    else:
        lowered = ""

    invocations = kwargs.get("invocation_params")
    if isinstance(invocations, dict):
        for key in ("model_name", "model"):
            if invocations.get(key):
                model = str(invocations[key])
                break

    if "anthropic" in lowered or "claude" in model.lower():
        provider = "anthropic"
    elif "openai" in lowered or "gpt" in model.lower() or model.startswith("o1"):
        provider = "openai"
    return provider, model


def _token_counts(response: Any) -> tuple[int | None, int | None]:
    """Extract (prompt_tokens, completion_tokens) from an LLMResult-like object."""
    usage: dict[str, Any] = {}
    llm_output = getattr(response, "llm_output", None)
    if isinstance(llm_output, dict):
        usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
    if isinstance(usage, dict) and (usage.get("prompt_tokens") or usage.get("completion_tokens")):
        return usage.get("prompt_tokens"), usage.get("completion_tokens")

    # newer chat models expose usage_metadata on the message
    try:
        message = response.generations[0][0].message
        meta = getattr(message, "usage_metadata", None)
        if isinstance(meta, dict):
            return meta.get("input_tokens"), meta.get("output_tokens")
    except Exception:  # noqa: BLE001 - shape differs across versions
        pass
    return None, None


class NectoCallbackHandler:
    """LangChain/LangGraph callback handler that emits necto events."""

    def __init__(
        self,
        necto: Necto,
        *,
        name: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.necto = necto
        self.name = name
        self.meta = dict(meta or {})
        self._run: Run | None = None
        self.last_run_id: str | None = None
        self._root_id: Any = None
        self._last_node: str | None = None
        self._chains: dict[Any, str | None] = {}
        self._llm_start: dict[Any, tuple[float, str]] = {}
        self._tool_start: dict[Any, tuple[str, float]] = {}

    # -- helpers -----------------------------------------------------------
    @property
    def run(self) -> Run | None:
        return self._run

    def _ensure_run(self, name: str | None) -> Run:
        if self._run is None:
            self._run = self.necto.start_run(name or self.name, self.meta)
            self.last_run_id = self._run.run_id
        return self._run

    def _node_for(self, run_id: Any) -> str | None:
        node = self._chains.get(run_id)
        return node or self._last_node

    def close(self) -> None:
        """Finish an in-flight run (safe to call twice)."""
        if self._run is not None:
            self._run.finish()
            self._run = None

    # -- chains ------------------------------------------------------------
    @_guard
    def on_chain_start(
        self,
        serialized: Any,
        inputs: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        tags: Any = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        node = _node_name(metadata, serialized, kwargs)

        if parent_run_id is None:
            # top-level chain: the graph itself starts the necto run
            self._root_id = run_id
            self._chains[run_id] = None
            self._ensure_run(node or self.name)
            return

        run = self._ensure_run(node or self.name)
        self._chains[run_id] = node

        is_node = bool(metadata and metadata.get("langgraph_node")) or (
            parent_run_id == self._root_id
        )
        if not is_node or not node:
            return

        if self._last_node is not None and self._last_node != node:
            run.handoff(self._last_node, node, reason="langgraph_edge")
        self._last_node = node
        run.agent_start(node, name=node)

    @_guard
    def on_chain_end(
        self,
        outputs: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        node = self._chains.get(run_id)
        if node and self._run is not None:
            self._run.agent_finish(node)
        if parent_run_id is None and run_id == self._root_id:
            self.close()

    @_guard
    def on_chain_error(
        self,
        error: BaseException | None,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        if self._run is not None:
            node = self._node_for(run_id) if self._chains.get(run_id) is None else self._chains[run_id]
            self._run.error(node or "unknown", str(error or "chain error"))

    # -- models ------------------------------------------------------------
    @_guard
    def on_llm_start(
        self,
        serialized: Any,
        prompts: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        provider, model = _model_name(serialized, kwargs)
        self._llm_start[run_id] = (time.monotonic(), f"{provider}:{model}")

    @_guard
    def on_chat_model_start(
        self,
        serialized: Any,
        messages: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self.on_llm_start(serialized, messages, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    @_guard
    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        if self._run is None:
            return
        started = self._llm_start.pop(run_id, None)
        latency_ms = int((time.monotonic() - started[0]) * 1000) if started else None
        provider, model = (started[1].split(":", 1) + ["unknown"])[:2] if started else ("unknown", "unknown")
        input_tokens, output_tokens = _token_counts(response)
        node = self._node_for(parent_run_id) or self._last_node or "unknown"
        self._run.llm_call(
            node,
            provider,
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

    @_guard
    def on_llm_error(
        self,
        error: BaseException | None,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        if self._run is not None:
            self._run.error(self._node_for(parent_run_id) or "unknown", str(error or "llm error"))

    # -- tools -------------------------------------------------------------
    @_guard
    def on_tool_start(
        self,
        serialized: Any,
        input_str: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        name = _node_name(None, serialized, kwargs) or "tool"
        self._tool_start[run_id] = (name, time.monotonic())
        if self._run is not None:
            node = self._node_for(parent_run_id) or self._last_node or "unknown"
            self._run.tool_call(node, name, name=name)

    @_guard
    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        if self._run is None:
            return
        started = self._tool_start.pop(run_id, None)
        name = started[0] if started else "tool"
        latency_ms = int((time.monotonic() - started[1]) * 1000) if started else None
        node = self._node_for(parent_run_id) or self._last_node or "unknown"
        self._run.tool_result(name, node, ok=True, latency_ms=latency_ms, output_snippet=str(output))

    @_guard
    def on_tool_error(
        self,
        error: BaseException | None,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        started = self._tool_start.pop(run_id, None)
        name = started[0] if started else "tool"
        if self._run is not None:
            node = self._node_for(parent_run_id) or self._last_node or "unknown"
            self._run.tool_result(name, node, ok=False)
            self._run.error(name, str(error or "tool error"))


def attach(handler: NectoCallbackHandler, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a LangChain/LangGraph `config` dict with the handler attached."""
    merged = dict(config or {})
    merged["callbacks"] = list(merged.get("callbacks") or []) + [handler]
    return merged
