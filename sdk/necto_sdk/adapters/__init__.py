"""Framework integrations.

Each adapter is import-safe without its framework installed: the framework is only
touched through duck-typed callbacks, never imported at module load.
"""

from .langgraph import NectoCallbackHandler, attach

__all__ = ["NectoCallbackHandler", "attach"]
