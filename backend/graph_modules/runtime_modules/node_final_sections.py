from __future__ import annotations

import asyncio
from typing import Any

from structures import CompleteDocument, ContentSection

from ..helpers import message_text


async def run_final_section_generation(
    state: dict[str, Any],
    *,
    emit_progress: Any,
    research_breadth: str,
    build_low_breadth_document: Any,
    generate_final_section: Any,
    repair_section_visualizations: Any,
    resolve_repair_task: Any,
    summary_model: Any,
    node_builder: Any,
    run_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await emit_progress("final_section_generation")
    if research_breadth == "low":
        return {"final_document": build_low_breadth_document(state)}

    generated_sections: list[ContentSection] = []
    repaired_sections: list[ContentSection | None] = []
    summary = None
    pending_repair_task: asyncio.Task[ContentSection] | None = None
    pending_repair_index: int | None = None

    for section_content in state["perspective_content"]:
        if len(section_content) == 0:
            continue
        final_section = await generate_final_section(
            section_content=section_content,
            outline_str=state["document_outline"].as_str,
            summary=summary,
        )
        generated_sections.append(final_section)
        repaired_sections.append(None)

        if pending_repair_task is not None and pending_repair_index is not None:
            repaired_sections[pending_repair_index] = await resolve_repair_task(
                pending_repair_task,
                generated_sections[pending_repair_index],
            )

        pending_repair_index = len(generated_sections) - 1
        pending_repair_task = asyncio.create_task(repair_section_visualizations(final_section))

        summary_message = await summary_model.ainvoke(
            node_builder.generate_rolling_summary(
                "\n".join([section.as_str for section in generated_sections])
            ),
            config=run_config,
        )
        summary = message_text(summary_message)

    if pending_repair_task is not None and pending_repair_index is not None:
        repaired_sections[pending_repair_index] = await resolve_repair_task(
            pending_repair_task,
            generated_sections[pending_repair_index],
        )

    final_sections = [section for section in repaired_sections if section is not None]
    final_document = CompleteDocument(
        title=state["document_outline"].document_title,
        sections=final_sections,
    )

    return {"final_document": final_document}
