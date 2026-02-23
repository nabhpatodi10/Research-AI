from __future__ import annotations

import asyncio
import inspect
from typing import Any


async def emit_progress(progress_callback: Any, node_name: str) -> None:
    if progress_callback is None:
        return
    try:
        maybe_result = progress_callback(node_name)
        if inspect.isawaitable(maybe_result):
            await maybe_result
    except asyncio.CancelledError:
        raise
    except Exception:
        # Progress events must never break the research pipeline.
        return


async def emit_state_checkpoint(
    checkpoint_callback: Any,
    *,
    completed_node: str,
    state: dict[str, Any],
    serialize_state: Any,
    next_node_after: Any,
) -> None:
    if checkpoint_callback is None:
        return
    try:
        maybe_result = checkpoint_callback(
            completed_node,
            serialize_state(state),
            next_node_after(completed_node),
        )
        if inspect.isawaitable(maybe_result):
            await maybe_result
    except asyncio.CancelledError:
        raise
    except Exception:
        # Checkpoint events must never break the research pipeline.
        return
