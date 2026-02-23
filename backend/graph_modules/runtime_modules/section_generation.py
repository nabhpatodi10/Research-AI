from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from langchain_core.messages import HumanMessage
from structures import CompleteDocument, ContentSection

from ..helpers import (
    extract_agent_text_content,
    fallback_section_text,
    is_structured_output_error,
    message_text,
)


async def invoke_section_agent(
    agent: object,
    prompt: str,
    *,
    run_config: dict[str, Any] | None = None,
) -> dict:
    return await agent.ainvoke({"messages": [HumanMessage(content=prompt)]}, config=run_config)


async def invoke_section_with_retry(
    *,
    agent: object,
    prompt: str,
    section_title: str,
    expert_label: str,
    section_retry_delays: tuple[float, ...],
    section_attempt_timeout_seconds: float,
    run_config: dict[str, Any] | None = None,
) -> str:
    attempt_count = len(section_retry_delays) + 1
    for attempt in range(1, attempt_count + 1):
        try:
            result = await asyncio.wait_for(
                invoke_section_agent(agent=agent, prompt=prompt, run_config=run_config),
                timeout=section_attempt_timeout_seconds,
            )
            content_text = extract_agent_text_content(result).strip()
            if content_text:
                return content_text
            raise ValueError("Generated section content was empty.")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if attempt >= attempt_count:
                print(
                    f"[graph] Expert '{expert_label}' failed for section '{section_title}' "
                    f"after {attempt_count} attempts: {error}. Using fallback content."
                )
                return fallback_section_text(section_title)

            delay = section_retry_delays[attempt - 1]
            print(
                f"[graph] Expert '{expert_label}' attempt {attempt}/{attempt_count} "
                f"failed for section '{section_title}': {error}. Retrying in {delay:.1f}s."
            )
            await asyncio.sleep(delay)

    return fallback_section_text(section_title)


async def run_expert_pipeline(
    *,
    expert_index: int,
    expert_name: str,
    expert_agent: object,
    sections: list,
    summary_model: Any,
    node_builder: Any,
    section_retry_delays: tuple[float, ...],
    section_attempt_timeout_seconds: float,
    run_config: dict[str, Any] | None = None,
) -> list[str]:
    start_time = perf_counter()
    print(f"[graph] Expert pipeline started: index={expert_index}, name='{expert_name}'")

    pipeline_outputs: list[str] = []
    expert_history: list[str] = []
    summary: str | None = None

    for section in sections:
        section_title = str(getattr(section, "section_title", "Untitled Section") or "Untitled Section")
        prompt = f"Write the content for the section:\n{section.as_str}"
        if summary:
            prompt += f"\n\nSummary of the previous sections:\n{summary}"

        section_text = await invoke_section_with_retry(
            agent=expert_agent,
            prompt=prompt,
            section_title=section_title,
            expert_label=expert_name,
            section_retry_delays=section_retry_delays,
            section_attempt_timeout_seconds=section_attempt_timeout_seconds,
            run_config=run_config,
        )
        pipeline_outputs.append(section_text)
        expert_history.append(f"## {section_title}\n\n{section_text}".strip())

        try:
            summary_message = await summary_model.ainvoke(
                node_builder.generate_rolling_summary("\n\n".join(expert_history)),
                config=run_config,
            )
            next_summary = message_text(summary_message).strip()
            if next_summary:
                summary = next_summary
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(
                f"[graph] Summary update failed for expert '{expert_name}' "
                f"after section '{section_title}': {error}. Continuing without summary update."
            )

    elapsed = perf_counter() - start_time
    print(
        f"[graph] Expert pipeline completed: index={expert_index}, "
        f"name='{expert_name}', sections={len(pipeline_outputs)}, elapsed={elapsed:.2f}s"
    )
    return pipeline_outputs


async def generate_final_section(
    *,
    section_content: list[str],
    outline_str: str,
    summary: str | None,
    node_builder: Any,
    final_content_model: Any,
    run_config: dict[str, Any] | None = None,
) -> ContentSection:
    messages = node_builder.generate_combined_section(
        "\n\n".join(section_content),
        outline_str,
        summary,
    )

    try:
        return await final_content_model.with_structured_output(ContentSection).ainvoke(
            messages,
            config=run_config,
        )
    except Exception as error:
        if not is_structured_output_error(error):
            raise

    return await final_content_model.with_structured_output(ContentSection).ainvoke(
        messages,
        config=run_config,
    )


def build_low_breadth_document(state: dict[str, Any]) -> CompleteDocument:
    sections = list(state["document_outline"].sections)
    perspective_rows = list(state.get("perspective_content", []))
    final_sections: list[ContentSection] = []

    for section_index, outline_section in enumerate(sections):
        section_title = str(
            getattr(outline_section, "section_title", f"Section {section_index + 1}")
            or f"Section {section_index + 1}"
        )
        section_text = ""
        if section_index < len(perspective_rows) and perspective_rows[section_index]:
            section_text = str(perspective_rows[section_index][0] or "").strip()
        if not section_text:
            section_text = fallback_section_text(section_title)

        final_sections.append(
            ContentSection(
                section_title=section_title,
                content=section_text,
                citations=[],
            )
        )

    return CompleteDocument(
        title=state["document_outline"].document_title,
        sections=final_sections,
    )
