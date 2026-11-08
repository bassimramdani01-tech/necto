"""Event helpers — produce dicts matching docs/SCHEMA.md (v1).

Kept dependency-free on purpose: the SDK should be installable anywhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1

ALLOWED_REF_KINDS = frozenset({"agent", "tool", "model", "external", "state"})


def utc_now_iso() -> str:
    """Current time as an RFC 3339 UTC string."""
    return datetime.now(timezone.utc).isoformat()


def ref(kind: str, identifier: str) -> str:
    """Build a 'kind:id' reference, e.g. ref('agent', 'router') -> 'agent:router'."""
    if kind not in ALLOWED_REF_KINDS:
        raise ValueError(f"unknown ref kind {kind!r}; expected one of {sorted(ALLOWED_REF_KINDS)}")
    if not identifier:
        raise ValueError("identifier must not be empty")
    return f"{kind}:{identifier}"


def agent(identifier: str) -> str:
    return ref("agent", identifier)


def tool(identifier: str) -> str:
    return ref("tool", identifier)


def model(provider: str, name: str) -> str:
    """Model refs are provider-namespaced: model:openai:gpt-4o-mini."""
    if not provider or not name:
        raise ValueError("provider and name must not be empty")
    return f"model:{provider}:{name}"


def external(identifier: str) -> str:
    return ref("external", identifier)


def state(identifier: str) -> str:
    return ref("state", identifier)


def event(
    type: str,
    payload: dict[str, Any] | None = None,
    from_ref: str | None = None,
    to_ref: str | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """Build a single event envelope."""
    return {
        "ts": ts or utc_now_iso(),
        "type": type,
        "schema_version": SCHEMA_VERSION,
        "from": from_ref,
        "to": to_ref,
        "payload": payload or {},
    }
