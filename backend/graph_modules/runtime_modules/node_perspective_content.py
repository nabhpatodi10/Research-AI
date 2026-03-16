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
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def update(
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

    async def flush_now(self) -> None:
        while True:
            snapshot = await self._snapshot()
            if snapshot is None:
                return

            revision, progress_message, checkpoint_state = snapshot
            if progress_message:
                await self._emit_progress("generate_content_for_perspectives", progress_message)
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

    async def _snapshot(self) -> tuple[int, str | None, dict[str, Any]] | None:
        async with self._lock:
            if self._dirty_revision <= self._flushed_revision:
                return None

            checkpoint_state = dict(self._state)
            if "expert_progress" in self._state:
                checkpoint_state["expert_progress"] = copy.deepcopy(self._state["expert_progress"])
            revision = self._dirty_revision
            return revision, self._latest_progress_message, checkpoint_state

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
            await progress_flusher.update(
                expert_index=_expert_index,
                expert_name=_expert_name,
                progress_payload=progress_payload,
                progress_message=progress_message,
            )

        expert_tasks.append(
            asyncio.create_task(
                run_expert_pipeline(
                    expert_index=expert_index,
                    expert_name=expert_name,
                    expert_agent=expert_agent,
                    sections=sections,
                    saved_progress=saved_progress if isinstance(saved_progress, dict) else None,
                    emit_progress=emit_progress,
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
