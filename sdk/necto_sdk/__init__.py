"""necto-sdk — instrument multi-agent AI apps for necto.

Quick start:

    from necto_sdk import Necto

    necto = Necto(endpoint="http://127.0.0.1:8000")

    with necto.run(name="demo") as run:
        run.handoff("router", "researcher", reason="needs sources")

Events are buffered and shipped in the background. The SDK never raises into
your application: if the necto server is down, events are dropped and logged.
"""

from ._version import __version__
from .events import agent, event, external, model, ref, state, tool
from .tracer import Necto, Run
from .transport import HttpTransport, NullTransport, RecordingTransport

__all__ = [
    "Necto",
    "Run",
    "HttpTransport",
    "NullTransport",
    "RecordingTransport",
    "agent",
    "event",
    "external",
    "model",
    "ref",
    "state",
    "tool",
    "__version__",
]
