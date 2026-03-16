from __future__ import annotations


class ResearchTerminalError(RuntimeError):
    """Marks a research failure as terminal so the worker does not requeue it."""

