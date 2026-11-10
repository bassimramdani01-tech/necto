"""Framework integrations.

Each adapter is import-safe without its framework installed: frameworks are only
touched through duck-typed callbacks, never imported at module load.
"""

from .langgraph import NectoCallbackHandler, attach
from .openai_agents import NectoProcessor, instrument

__all__ = ["NectoCallbackHandler", "NectoProcessor", "attach", "instrument"]
