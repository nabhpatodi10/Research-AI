from __future__ import annotations

import asyncio
from typing import Any

from structures import CompleteDocument, ContentSection

from ..helpers import fallback_section_text, message_text
from .errors import ResearchTerminalError
from .section_generation import is_context_window_error


async def compact_final_summary(
    *,
    summary_model: Any,
    node_builder: Any,
    summary: str | None,
    run_config: dict[str, Any] | None = None,
) -> str | None:
    current_summary = str(summary or "").strip()
    if not current_summary:
        return summary

    summary_message = await summary_model.ainvoke(
        node_builder.generate_rolling_summary(current_summary),
        config=run_config,
    )
    next_summary = message_text(summary_message).strip()
    return next_summary or current_summary


async def run_final_section_generation(
    state: dict[str, Any],
    *,
    emit_progress: Any,
    emit_state_checkpoint: Any,
    research_breadth: str,
    build_low_breadth_document: Any,
    generate_final_section: Any,
    repair_section_visualizations: Any,
    repair_section_equations: Any,
    resolve_repair_task: Any,
    summary_model: Any,
    node_builder: Any,
    run_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await emit_progress("final_section_generation")
    if research_breadth == "low":
        state.pop("final_section_progress", None)
        return {"final_document": build_low_breadth_document(state)}

    perspective_rows = list(state.get("perspective_content", []))
    sections = list(state["document_outline"].sections)
    saved_progress = state.get("final_section_progress") if isinstance(state.get("final_section_progress"), dict) else {}
    completed_sections = [
        section
        for section in list(saved_progress.get("completed_sections") or [])[: len(perspective_rows)]
        if isinstance(section, ContentSection)
    ]
    summary = str(saved_progress.get("summary") or "").strip() or None

    if len(completed_sections) > 0:
        await emit_progress(
            "final_section_generation",
            (
                "Resuming final document generation from section "
                f"{min(len(completed_sections) + 1, len(perspective_rows))}/{max(len(perspective_rows), 1)}."
            ),
        )

    for section_index in range(len(completed_sections), len(perspective_rows)):
        section = sections[section_index]
        section_title = str(getattr(section, "section_title", f"Section {section_index + 1}") or f"Section {section_index + 1}")
        section_content = [
            str(item or "").strip() for item in perspective_rows[section_index] if str(item or "").strip()
        ]
        if len(section_content) == 0:
            section_content = [fallback_section_text(section_title)]

        final_section: ContentSection | None = None
        for attempt in range(3):
            attempt_label = "initial attempt" if attempt == 0 else f"retry {attempt}/2"
            await emit_progress(
                "final_section_generation",
                f"Generating final section {section_index + 1}/{len(perspective_rows)} ({attempt_label}).",
            )
            try:
                generated_section = await generate_final_section(
                    section_content=section_content,
                    outline_str=state["document_outline"].as_str,
                    summary=summary,
                )
                viz_repaired = await resolve_repair_task(
                    asyncio.create_task(repair_section_visualizations(generated_section)),
                    generated_section,
                )
                final_section = await repair_section_equations(
                    viz_repaired
                )

                next_sections = [*completed_sections, final_section]
                summary_message = await summary_model.ainvoke(
                    node_builder.generate_rolling_summary(
                        "\n".join([section_item.as_str for section_item in next_sections])
                    ),
                    config=run_config,
                )
                next_summary = message_text(summary_message).strip()
                summary = next_summary or summary
                completed_sections = next_sections
                state["final_section_progress"] = {
                    "summary": summary or "",
                    "completed_sections": list(completed_sections),
                }
                await emit_progress(
                    "final_section_generation",
                    f"Completed final section {section_index + 1}/{len(perspective_rows)}.",
                )
                await emit_state_checkpoint(state, "final_section_generation")
                break
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if attempt >= 2:
                    raise ResearchTerminalError(
                        "Final section generation failed after 1 initial attempt and 2 retries "
                        f"for '{section_title}': {error}"
                    ) from error
                if is_context_window_error(error):
                    try:
                        summary = await compact_final_summary(
                            summary_model=summary_model,
                            node_builder=node_builder,
                            summary=summary,
                            run_config=run_config,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as summary_error:
                        print(
                            f"[graph] Final-section summary compaction failed for '{section_title}': "
                            f"{summary_error}"
                        )
                print(
                    f"[graph] Final section {section_index + 1}/{len(perspective_rows)} "
                    f"attempt {attempt + 1}/3 failed for '{section_title}': {error}"
                )
        if final_section is None:
            raise ResearchTerminalError(
                f"Final section generation did not produce a section for '{section_title}'."
            )

    state.pop("final_section_progress", None)
    final_document = CompleteDocument(
        title=state["document_outline"].document_title,
        sections=completed_sections,
    )
    return {"final_document": final_document}
