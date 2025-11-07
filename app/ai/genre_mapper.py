"""Compatibility shim for legacy imports.

This module re-exports symbols from `local_fallback.py` so older code
that imports `app.ai.genre_mapper` keeps working.
"""

from .local_fallback import *  # noqa: F401,F403
