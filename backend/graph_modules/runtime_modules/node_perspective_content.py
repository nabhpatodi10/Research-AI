from __future__ import annotations

import asyncio
from typing import Any

from langchain.agents import create_agent

from ..helpers import fallback_section_text


async def run_generate_content_for_perspectives(
    state: dict[str, Any],
    *,
    emit_progress: Any,
    gpt_model: Any,
    gemini_model: Any,
    node_builder: Any,
    tools: list[Any],
    run_expert_pipeline: Any,
) -> dict[str, Any]:
    await emit_progress("generate_content_for_perspectives")
    sections = list(state["document_outline"].sections)
    if len(sections) == 0:
        return {"perspective_content": []}

    expert_agents: list[tuple[int, str, object]] = []
    for index, expert in enumerate(state["perspectives"].experts):
        model = gpt_model if index % 2 == 0 else gemini_model
        system_prompt = node_builder.perspective_agent(expert, state["document_outline"].as_str)
        expert_agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
        )
        expert_name = str(getattr(expert, "name", f"Expert {index + 1}") or f"Expert {index + 1}")
        expert_agents.append((index, expert_name, expert_agent))

    if len(expert_agents) == 0:
        return {"perspective_content": []}

    expert_tasks = [
        asyncio.create_task(
            run_expert_pipeline(
                expert_index=expert_index,
                expert_name=expert_name,
                expert_agent=expert_agent,
                sections=sections,
            )
        )
        for expert_index, expert_name, expert_agent in expert_agents
    ]

    pipeline_results = await asyncio.gather(*expert_tasks, return_exceptions=True)

    expert_outputs: list[list[str]] = []
    for result_index, result in enumerate(pipeline_results):
        if isinstance(result, Exception):
            failing_expert = expert_agents[result_index][1]
            print(
                f"[graph] Expert pipeline '{failing_expert}' crashed with: {result}. "
                "Using fallback content for all sections."
            )
            expert_outputs.append(
                [fallback_section_text(section.section_title) for section in sections]
            )
            continue

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
            row.append(text if text else fallback_section_text(section.section_title))
        perspective_content.append(row)

    return {"perspective_content": perspective_content}
