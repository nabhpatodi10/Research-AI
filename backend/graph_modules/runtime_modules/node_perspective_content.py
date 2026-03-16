from __future__ import annotations

import asyncio
import copy
import inspect
from typing import Any

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from ..helpers import fallback_section_text
from .expert_context import (
    EXPERT_CONTEXT_SUMMARY_PROMPT as HIGH_FIDELITY_SUMMARY_PROMPT,
    ExpertContextSummarizationMiddleware,
)
from .errors import ResearchOwnershipLostError
from .section_generation import normalize_saved_section_results


_ACTIVE_EXPERT_STATUSES = {"writing", "warm_retry", "cold_retry", "compacting"}


def _build_expert_display_text(
    *,
    index: int,
    name: str,
    status: str,
    status_label: str,
    section_index: int | None,
    section_total: int | None,
    section_title: str | None,
) -> str:
    prefix = f"Expert {index + 1}: {name}"
    normalized_status = str(status or "").strip().lower()
    normalized_title = str(section_title or "").strip()
    has_section = section_index is not None and section_total is not None
    section_suffix = (
        f" (Section {section_index}/{section_total})"
        if has_section
        else ""
    )
    if normalized_status == "completed":
        if section_total is not None:
            return f"{prefix} - Completed all sections ({section_total}/{section_total})"
        return f"{prefix} - Completed"
    if normalized_status == "skipped":
        title_text = normalized_title or "current section"
        return f"{prefix} - Skipped {title_text}{section_suffix}"
    if normalized_status == "compacting":
        title_text = normalized_title or "current section"
        return f"{prefix} - Compacting context for {title_text}{section_suffix}"
    if normalized_status == "queued":
        title_text = normalized_title or "next section"
        return f"{prefix} - Queued for {title_text}{section_suffix}"
    title_text = normalized_title or "current section"
    return f"{prefix} - {status_label} {title_text}{section_suffix}"


def _build_expert_status_entry(
    *,
    expert_index: int,
    expert_name: str,
    status: str,
    status_label: str,
    section_index: int | None,
    section_total: int | None,
    section_title: str | None,
) -> dict[str, Any]:
    normalized_section_index = int(section_index) if section_index is not None else None
    normalized_section_total = int(section_total) if section_total is not None else None
    normalized_title = str(section_title or "").strip() or None
    normalized_status = str(status or "").strip().lower() or "queued"
    normalized_status_label = str(status_label or "").strip() or "Queued"
    return {
        "index": int(expert_index),
        "name": str(expert_name or f"Expert {expert_index + 1}"),
        "status": normalized_status,
        "status_label": normalized_status_label,
        "section_index": normalized_section_index,
        "section_total": normalized_section_total,
        "section_title": normalized_title,
        "display_text": _build_expert_display_text(
            index=int(expert_index),
            name=str(expert_name or f"Expert {expert_index + 1}"),
            status=normalized_status,
            status_label=normalized_status_label,
            section_index=normalized_section_index,
            section_total=normalized_section_total,
            section_title=normalized_title,
        ),
    }


def _build_initial_expert_status_entry(
    *,
    expert_index: int,
    expert_name: str,
    sections: list[Any],
    saved_progress: dict[str, Any] | None,
) -> dict[str, Any]:
    section_results = normalize_saved_section_results(saved_progress, sections)
    total_sections = len(sections)
    if total_sections == 0:
        return _build_expert_status_entry(
            expert_index=expert_index,
            expert_name=expert_name,
            status="completed",
            status_label="Completed",
            section_index=None,
            section_total=None,
            section_title=None,
        )

    if len(section_results) >= total_sections:
        last_title = str(
            getattr(sections[-1], "section_title", f"Section {total_sections}") or f"Section {total_sections}"
        )
        return _build_expert_status_entry(
            expert_index=expert_index,
            expert_name=expert_name,
            status="completed",
            status_label="Completed",
            section_index=total_sections,
            section_total=total_sections,
            section_title=last_title,
        )

    next_section = sections[len(section_results)]
    next_title = str(
        getattr(next_section, "section_title", f"Section {len(section_results) + 1}")
        or f"Section {len(section_results) + 1}"
    )
    return _build_expert_status_entry(
        expert_index=expert_index,
        expert_name=expert_name,
        status="queued",
        status_label="Queued",
        section_index=len(section_results) + 1,
        section_total=total_sections,
        section_title=next_title,
    )


def _build_expert_progress_details(expert_statuses: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(expert_statuses, dict) or len(expert_statuses) == 0:
        return None

    ordered = [
        expert_statuses[key]
        for key in sorted(expert_statuses, key=lambda value: int(value))
        if isinstance(expert_statuses.get(key), dict)
    ]
    if len(ordered) == 0:
        return None

    total = len(ordered)
    active = sum(
        1
        for entry in ordered
        if str(entry.get("status") or "").strip().lower() in _ACTIVE_EXPERT_STATUSES
    )
    completed = sum(
        1
        for entry in ordered
        if str(entry.get("status") or "").strip().lower() == "completed"
    )
    queued = sum(
        1
        for entry in ordered
        if str(entry.get("status") or "").strip().lower() == "queued"
    )

    if completed >= total:
        summary_text = f"All {total} experts finished writing."
    elif active > 0:
        summary_text = f"{active} of {total} experts actively writing."
    elif queued >= total:
        summary_text = f"Preparing {total} experts to write their sections."
    else:
        summary_text = f"{completed} of {total} experts completed."

    return {
        "kind": "expert_progress",
        "summary_text": summary_text,
        "experts": ordered,
    }


async def _emit_progress_update(
    emit_progress: Any,
    node_name: str,
    progress_message: str | None = None,
    progress_details: dict[str, Any] | None = None,
) -> None:
    if emit_progress is None:
        return

    try:
        signature = inspect.signature(emit_progress)
    except (TypeError, ValueError):
        signature = None

    if signature is None:
        try:
            maybe_result = emit_progress(node_name, progress_message, progress_details)
        except TypeError:
            try:
                maybe_result = emit_progress(node_name, progress_message)
            except TypeError:
                maybe_result = emit_progress(node_name)
    else:
        parameters = signature.parameters
        supports_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        positional_count = len(
            [
                parameter
                for parameter in parameters.values()
                if parameter.kind
                in {
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                }
            ]
        )
        if positional_count >= 3 or supports_kwargs:
            maybe_result = emit_progress(node_name, progress_message, progress_details)
        elif positional_count >= 2:
            maybe_result = emit_progress(node_name, progress_message)
        else:
            maybe_result = emit_progress(node_name)

    if inspect.isawaitable(maybe_result):
        await maybe_result


class _ExpertProgressFlusher:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        emit_progress: Any,
        emit_state_checkpoint: Any,
    ) -> None:
        self._state = state
        self._emit_progress = emit_progress
        self._emit_state_checkpoint = emit_state_checkpoint
        self._lock = asyncio.Lock()
        self._wake_event = asyncio.Event()
        self._closed = False
        self._dirty_revision = 0
        self._flushed_revision = 0
        self._latest_progress_message: str | None = None
        self._expert_statuses: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def seed_statuses(self, entries: list[dict[str, Any]]) -> None:
        async with self._lock:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                index = str(int(entry.get("index") or 0))
                self._expert_statuses[index] = dict(entry)
            self._dirty_revision += 1
            self._wake_event.set()

    async def update_saved_progress(
        self,
        *,
        expert_index: int,
        expert_name: str,
        progress_payload: dict[str, Any],
        progress_message: str,
    ) -> None:
        async with self._lock:
            expert_progress_state = self._state.setdefault("expert_progress", {"experts": {}})
            experts_state = expert_progress_state.setdefault("experts", {})
            experts_state[str(expert_index)] = {
                "expert_name": expert_name,
                "summary": str(progress_payload.get("summary") or ""),
                "section_results": list(progress_payload.get("section_results") or []),
            }
            self._dirty_revision += 1
            self._latest_progress_message = str(progress_message or "").strip() or None
            self._wake_event.set()

    async def update_status(
        self,
        *,
        expert_index: int,
        status_entry: dict[str, Any],
    ) -> None:
        async with self._lock:
            self._expert_statuses[str(expert_index)] = dict(status_entry)
            self._dirty_revision += 1
            self._wake_event.set()

    async def flush_now(self) -> None:
        while True:
            snapshot = await self._snapshot()
            if snapshot is None:
                return

            revision, progress_message, progress_details, checkpoint_state = snapshot
            if progress_message:
                await _emit_progress_update(
                    self._emit_progress,
                    "generate_content_for_perspectives",
                    progress_message,
                    progress_details,
                )
            await self._emit_state_checkpoint(
                checkpoint_state,
                "generate_content_for_perspectives",
            )
            await self._mark_flushed(revision)

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            self._wake_event.set()
        if self._task is not None:
            try:
                await self._task
            finally:
                self._task = None

    async def _snapshot(self) -> tuple[int, str | None, dict[str, Any] | None, dict[str, Any]] | None:
        async with self._lock:
            if self._dirty_revision <= self._flushed_revision:
                return None

            checkpoint_state = dict(self._state)
            if "expert_progress" in self._state:
                checkpoint_state["expert_progress"] = copy.deepcopy(self._state["expert_progress"])
            revision = self._dirty_revision
            progress_details = _build_expert_progress_details(copy.deepcopy(self._expert_statuses))
            progress_message = (
                str(progress_details.get("summary_text") or "").strip()
                if isinstance(progress_details, dict)
                else self._latest_progress_message
            )
            return revision, progress_message or None, progress_details, checkpoint_state

    async def _mark_flushed(self, revision: int) -> None:
        async with self._lock:
            self._flushed_revision = max(self._flushed_revision, revision)
            if self._dirty_revision > self._flushed_revision:
                self._wake_event.set()

    async def _run(self) -> None:
        while True:
            await self._wake_event.wait()
            self._wake_event.clear()
            await self.flush_now()
            async with self._lock:
                should_stop = self._closed and self._dirty_revision <= self._flushed_revision
            if should_stop:
                return


def _saved_progress_to_expert_output(
    *,
    sections: list[Any],
    saved_progress: dict[str, Any] | None,
) -> list[str] | None:
    section_results = normalize_saved_section_results(saved_progress, sections)
    if len(section_results) < len(sections):
        return None

    output: list[str] = []
    for section_index in range(len(sections)):
        result = section_results[section_index]
        if str(result.get("status") or "").strip().lower() == "skipped":
            output.append("")
            continue
        output.append(str(result.get("content") or ""))
    return output


def _build_perspective_content_from_expert_outputs(
    *,
    sections: list[Any],
    expert_outputs: list[list[str]],
) -> list[list[str]]:
    perspective_content: list[list[str]] = []
    for section_index, section in enumerate(sections):
        row: list[str] = []
        for expert_output in expert_outputs:
            if section_index >= len(expert_output):
                continue
            text = str(expert_output[section_index] or "").strip()
            if text:
                row.append(text)
        if len(row) == 0:
            row.append(fallback_section_text(section.section_title))
        perspective_content.append(row)
    return perspective_content


async def _emit_checkpoint(
    emit_state_checkpoint: Any,
    state: dict[str, Any],
    node_name: str,
    *,
    resume_from_node: str | None = None,
) -> None:
    if emit_state_checkpoint is None:
        return

    try:
        signature = inspect.signature(emit_state_checkpoint)
    except (TypeError, ValueError):
        signature = None

    if signature is None:
        if resume_from_node is None:
            maybe_result = emit_state_checkpoint(state, node_name)
        else:
            maybe_result = emit_state_checkpoint(state, node_name, resume_from_node)
    else:
        parameters = signature.parameters
        supports_keyword = (
            "resume_from_node" in parameters
            or any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
        )
        supports_positional = (
            len(parameters) >= 3
            or any(
                parameter.kind == inspect.Parameter.VAR_POSITIONAL
                for parameter in parameters.values()
            )
        )
        if resume_from_node is None:
            maybe_result = emit_state_checkpoint(state, node_name)
        elif supports_keyword:
            maybe_result = emit_state_checkpoint(
                state,
                node_name,
                resume_from_node=resume_from_node,
            )
        elif supports_positional:
            maybe_result = emit_state_checkpoint(state, node_name, resume_from_node)
        else:
            maybe_result = emit_state_checkpoint(state, node_name)

    if inspect.isawaitable(maybe_result):
        await maybe_result


async def run_generate_content_for_perspectives(
    state: dict[str, Any],
    *,
    emit_progress: Any,
    emit_state_checkpoint: Any,
    gpt_model: Any,
    gemini_model: Any,
    summary_model: Any,
    node_builder: Any,
    tools: list[Any],
    run_expert_pipeline: Any,
    expert_context_summarization_enabled: bool,
    expert_context_summary_trigger_tokens: int,
    expert_context_summary_keep_messages: int,
    expert_context_summary_trim_tokens_to_summarize: int,
) -> dict[str, Any]:
    await emit_progress("generate_content_for_perspectives")
    sections = list(state["document_outline"].sections)
    if len(sections) == 0:
        state.pop("expert_progress", None)
        return {"perspective_content": []}

    existing_perspective_content = state.get("perspective_content")
    if isinstance(existing_perspective_content, list) and len(existing_perspective_content) == len(sections):
        await _emit_checkpoint(
            emit_state_checkpoint,
            state,
            "generate_content_for_perspectives",
            resume_from_node="final_section_generation",
        )
        state.pop("expert_progress", None)
        return {"perspective_content": existing_perspective_content}

    saved_expert_progress = (
        state.get("expert_progress", {}).get("experts", {})
        if isinstance(state.get("expert_progress"), dict)
        else {}
    )
    experts = list(state["perspectives"].experts)
    expert_specs: list[tuple[int, str, Any]] = []
    expert_outputs_by_index: dict[int, list[str]] = {}

    for index, expert in enumerate(experts):
        expert_name = str(getattr(expert, "name", f"Expert {index + 1}") or f"Expert {index + 1}")
        saved_progress = saved_expert_progress.get(str(index))
        saved_output = _saved_progress_to_expert_output(
            sections=sections,
            saved_progress=saved_progress if isinstance(saved_progress, dict) else None,
        )
        if saved_output is not None:
            expert_outputs_by_index[index] = saved_output
            continue
        expert_specs.append((index, expert_name, expert))

    if len(experts) > 0 and len(expert_outputs_by_index) == len(experts):
        ordered_outputs = [
            expert_outputs_by_index[index]
            for index in range(len(experts))
        ]
        perspective_content = _build_perspective_content_from_expert_outputs(
            sections=sections,
            expert_outputs=ordered_outputs,
        )
        state["perspective_content"] = perspective_content
        await _emit_checkpoint(
            emit_state_checkpoint,
            state,
            "generate_content_for_perspectives",
            resume_from_node="final_section_generation",
        )
        state.pop("expert_progress", None)
        return {"perspective_content": perspective_content}

    progress_flusher: _ExpertProgressFlusher | None = None
    if len(expert_specs) > 0:
        progress_flusher = _ExpertProgressFlusher(
            state=state,
            emit_progress=emit_progress,
            emit_state_checkpoint=emit_state_checkpoint,
        )
        progress_flusher.start()
    expert_agents: list[tuple[int, str, object]] = []
    for index, expert_name, expert in expert_specs:
        model = gpt_model if index % 2 == 0 else gemini_model
        system_prompt = node_builder.perspective_agent(expert, state["document_outline"].as_str)
        middleware = []
        if expert_context_summarization_enabled:
            middleware = [
                ExpertContextSummarizationMiddleware(
                    summary_model=summary_model,
                    trigger_tokens=max(1, int(expert_context_summary_trigger_tokens)),
                    keep_last_messages=max(1, int(expert_context_summary_keep_messages)),
                    trim_tokens_to_summarize=max(
                        1,
                        int(expert_context_summary_trim_tokens_to_summarize),
                    ),
                    summary_prompt=HIGH_FIDELITY_SUMMARY_PROMPT,
                )
            ]
        expert_agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            middleware=middleware,
            checkpointer=InMemorySaver(),
        )
        expert_agents.append((index, expert_name, expert_agent))

    if len(experts) == 0:
        state.pop("expert_progress", None)
        return {"perspective_content": []}

    expert_tasks: list[asyncio.Task[list[str]]] = []
    if progress_flusher is not None:
        initial_statuses = [
            _build_initial_expert_status_entry(
                expert_index=index,
                expert_name=str(getattr(expert, "name", f"Expert {index + 1}") or f"Expert {index + 1}"),
                sections=sections,
                saved_progress=(
                    saved_expert_progress.get(str(index))
                    if isinstance(saved_expert_progress.get(str(index)), dict)
                    else None
                ),
            )
            for index, expert in enumerate(experts)
        ]
        await progress_flusher.seed_statuses(initial_statuses)

    for expert_index, expert_name, expert_agent in expert_agents:
        saved_progress = saved_expert_progress.get(str(expert_index))
        async def _persist_for_expert(
            progress_payload: dict[str, Any],
            progress_message: str,
            *,
            _expert_index: int = expert_index,
            _expert_name: str = expert_name,
        ) -> None:
            assert progress_flusher is not None
            await progress_flusher.update_saved_progress(
                expert_index=_expert_index,
                expert_name=_expert_name,
                progress_payload=progress_payload,
                progress_message=progress_message,
            )

        async def _emit_status_for_expert(
            status_payload: dict[str, Any],
            *,
            _expert_index: int = expert_index,
            _expert_name: str = expert_name,
        ) -> None:
            assert progress_flusher is not None
            await progress_flusher.update_status(
                expert_index=_expert_index,
                status_entry=_build_expert_status_entry(
                    expert_index=_expert_index,
                    expert_name=_expert_name,
                    status=str(status_payload.get("status") or "queued"),
                    status_label=str(status_payload.get("status_label") or "Queued"),
                    section_index=status_payload.get("section_index"),
                    section_total=status_payload.get("section_total"),
                    section_title=status_payload.get("section_title"),
                ),
            )

        expert_tasks.append(
            asyncio.create_task(
                run_expert_pipeline(
                    expert_index=expert_index,
                    expert_name=expert_name,
                    expert_agent=expert_agent,
                    sections=sections,
                    saved_progress=saved_progress if isinstance(saved_progress, dict) else None,
                    emit_expert_status=_emit_status_for_expert,
                    persist_progress=_persist_for_expert,
                )
            )
        )

    try:
        pipeline_results = await asyncio.gather(*expert_tasks, return_exceptions=True)
        if progress_flusher is not None:
            await progress_flusher.flush_now()
    finally:
        if progress_flusher is not None:
            await progress_flusher.close()

    for result_index, result in enumerate(pipeline_results):
        if isinstance(result, Exception):
            if isinstance(result, ResearchOwnershipLostError):
                raise result
            failing_expert = expert_agents[result_index][1]
            raise RuntimeError(
                f"Expert pipeline '{failing_expert}' crashed unexpectedly."
            ) from result

        normalized = list(result)
        if len(normalized) < len(sections):
            missing = len(sections) - len(normalized)
            normalized.extend(
                [
                    fallback_section_text(sections[len(normalized) + offset].section_title)
                    for offset in range(missing)
                ]
            )
        elif len(normalized) > len(sections):
            normalized = normalized[: len(sections)]

        expert_outputs_by_index[expert_agents[result_index][0]] = normalized

    ordered_outputs = [
        expert_outputs_by_index[index]
        for index in range(len(experts))
        if index in expert_outputs_by_index
    ]
    perspective_content = _build_perspective_content_from_expert_outputs(
        sections=sections,
        expert_outputs=ordered_outputs,
    )
    state["perspective_content"] = perspective_content
    await _emit_checkpoint(
        emit_state_checkpoint,
        state,
        "generate_content_for_perspectives",
        resume_from_node="final_section_generation",
    )
    state.pop("expert_progress", None)
    return {"perspective_content": perspective_content}
