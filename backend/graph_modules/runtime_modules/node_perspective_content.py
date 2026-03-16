from __future__ import annotations

import asyncio
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from ..helpers import fallback_section_text


HIGH_FIDELITY_SUMMARY_PROMPT = """
Summarize the prior conversation context for a specialist research agent.

You must preserve critical information with high fidelity. Do not fabricate information.
If a section has nothing relevant, write "None".

Use exactly this structure:

## SESSION GOAL
State the overall research objective and what this specialist is currently trying to produce.

## REQUIRED CONSTRAINTS
Capture all explicit constraints and requirements (formatting, scope, exclusions, quality bars, citation rules, equation/chart requirements, etc.).

## KEY DECISIONS
List important decisions already made, including rationale when present.

## TOOL FINDINGS
Summarize important tool outcomes and factual findings, including contradictions or uncertainty.

## SOURCES / CITATIONS
List important URLs or source references already established.

## OPEN QUESTIONS / ASSUMPTIONS
Capture unresolved questions, assumptions, and pending clarifications.

## EXECUTION STATE
Describe what has already been completed and what remains to be done next.

Return only the structured summary.

Messages to summarize:
{messages}
""".strip()


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

    saved_expert_progress = (
        state.get("expert_progress", {}).get("experts", {})
        if isinstance(state.get("expert_progress"), dict)
        else {}
    )
    checkpoint_lock = asyncio.Lock()
    expert_agents: list[tuple[int, str, object]] = []
    for index, expert in enumerate(state["perspectives"].experts):
        model = gpt_model if index % 2 == 0 else gemini_model
        system_prompt = node_builder.perspective_agent(expert, state["document_outline"].as_str)
        middleware = []
        if expert_context_summarization_enabled:
            middleware = [
                SummarizationMiddleware(
                    model=summary_model,
                    trigger=("tokens", max(1, int(expert_context_summary_trigger_tokens))),
                    keep=("messages", max(1, int(expert_context_summary_keep_messages))),
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
        expert_name = str(getattr(expert, "name", f"Expert {index + 1}") or f"Expert {index + 1}")
        expert_agents.append((index, expert_name, expert_agent))

    if len(expert_agents) == 0:
        state.pop("expert_progress", None)
        return {"perspective_content": []}

    async def _persist_expert_progress(
        expert_index: int,
        expert_name: str,
        progress_payload: dict[str, Any],
        progress_message: str,
    ) -> None:
        async with checkpoint_lock:
            expert_progress_state = state.setdefault("expert_progress", {"experts": {}})
            experts_state = expert_progress_state.setdefault("experts", {})
            experts_state[str(expert_index)] = {
                "expert_name": expert_name,
                "summary": str(progress_payload.get("summary") or ""),
                "section_results": list(progress_payload.get("section_results") or []),
            }
            await emit_progress("generate_content_for_perspectives", progress_message)
            await emit_state_checkpoint(state, "generate_content_for_perspectives")

    expert_tasks = []
    for expert_index, expert_name, expert_agent in expert_agents:
        saved_progress = saved_expert_progress.get(str(expert_index))
        async def _persist_for_expert(
            progress_payload: dict[str, Any],
            progress_message: str,
            *,
            _expert_index: int = expert_index,
            _expert_name: str = expert_name,
        ) -> None:
            await _persist_expert_progress(
                _expert_index,
                _expert_name,
                progress_payload,
                progress_message,
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

    pipeline_results = await asyncio.gather(*expert_tasks, return_exceptions=True)

    expert_outputs: list[list[str]] = []
    for result_index, result in enumerate(pipeline_results):
        if isinstance(result, Exception):
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

        expert_outputs.append(normalized)

    perspective_content: list[list[str]] = []
    for section_index, section in enumerate(sections):
        row: list[str] = []
        for expert_index in range(len(expert_outputs)):
            value = expert_outputs[expert_index][section_index]
            text = str(value or "").strip()
            if text:
                row.append(text)
        if len(row) == 0:
            row.append(fallback_section_text(section.section_title))
        perspective_content.append(row)

    state.pop("expert_progress", None)
    return {"perspective_content": perspective_content}
