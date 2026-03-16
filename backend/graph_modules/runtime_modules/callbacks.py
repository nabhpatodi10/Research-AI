from __future__ import annotations

import asyncio
import inspect
from typing import Any

from .errors import ResearchOwnershipLostError


async def _resolve_callback_result(
    maybe_result: Any,
    *,
    timeout_seconds: float | None,
) -> Any:
    if not inspect.isawaitable(maybe_result):
        return maybe_result
    if timeout_seconds is None or timeout_seconds <= 0:
        return await maybe_result
    return await asyncio.wait_for(maybe_result, timeout=float(timeout_seconds))


async def emit_progress(
    progress_callback: Any,
    node_name: str,
    progress_message: str | None = None,
    progress_details: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> bool:
    if progress_callback is None:
        return True
    try:
        try:
            maybe_result = progress_callback(node_name, progress_message, progress_details)
        except TypeError:
            try:
                maybe_result = progress_callback(node_name, progress_message)
            except TypeError:
                maybe_result = progress_callback(node_name)
        result = await _resolve_callback_result(
            maybe_result,
            timeout_seconds=timeout_seconds,
        )
        return result is not False
    except ResearchOwnershipLostError:
        raise
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return False
    except Exception:
        # Progress events must never break the research pipeline.
        return False


async def emit_state_checkpoint(
    checkpoint_callback: Any,
    *,
    completed_node: str,
    state: dict[str, Any],
    serialize_state: Any,
    next_node_after: Any,
    resume_from_node: str | None = None,
    timeout_seconds: float | None = None,
) -> bool:
    if checkpoint_callback is None:
        return True
    try:
        maybe_result = checkpoint_callback(
            completed_node,
            serialize_state(state),
            next_node_after(completed_node)
            if resume_from_node is None
            else str(resume_from_node or "").strip() or None,
        )
        result = await _resolve_callback_result(
            maybe_result,
            timeout_seconds=timeout_seconds,
        )
        return result is not False
    except ResearchOwnershipLostError:
        raise
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return False
    except Exception:
        # Checkpoint events must never break the research pipeline.
        return False
