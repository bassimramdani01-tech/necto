"""Framework integrations.

Each adapter is import-safe without its framework installed: frameworks are only
touched through duck-typed callbacks, never imported at module load.
"""

from .langgraph import NectoCallbackHandler, attach
from .openai_agents import NectoProcessor
from .openai_agents import instrument as instrument_openai_agents
from .otel import NectoSpanProcessor
from .otel import instrument as instrument_otel

__all__ = [
    "NectoCallbackHandler",
    "NectoProcessor",
    "NectoSpanProcessor",
    "attach",
    "instrument_openai_agents",
    "instrument_otel",
]
