from __future__ import annotations


class ResearchTerminalError(RuntimeError):
    """Marks a research failure as terminal so the worker does not requeue it."""


class ResearchOwnershipLostError(RuntimeError):
    """Raised when a worker loses ownership of a running research job."""
