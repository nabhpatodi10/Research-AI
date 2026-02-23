from __future__ import annotations

import asyncio
from typing import Any

from structures import ContentSection

from ..helpers import message_text
from ..visualizations import (
    InvalidVisualBlock,
    SectionValidationReport,
    ValidationResult,
    extract_visual_blocks,
    validate_chartjson_async,
    validate_mermaid_async,
    validate_section_visualizations_async,
)


async def validate_section_visualizations(
    content: str,
    *,
    tier2_validator: Any,
    tier2_enabled: bool,
    tier2_fail_open: bool,
) -> SectionValidationReport:
    return await validate_section_visualizations_async(
        content,
        tier2_validator=tier2_validator,
        tier2_enabled=tier2_enabled,
        tier2_fail_open=tier2_fail_open,
    )


def _replace_span(source: str, start: int, end: int, replacement: str) -> str:
    normalized_source = str(source or "")
    safe_start = max(0, min(len(normalized_source), int(start)))
    safe_end = max(safe_start, min(len(normalized_source), int(end)))
    return normalized_source[:safe_start] + str(replacement) + normalized_source[safe_end:]


def _remove_span(source: str, start: int, end: int) -> str:
    return _replace_span(source, start, end, "")


def _remove_invalid_spans(source: str, invalid_blocks: list[InvalidVisualBlock]) -> str:
    cleaned = str(source or "")
    for invalid in sorted(invalid_blocks, key=lambda item: item.block.start, reverse=True):
        cleaned = _remove_span(cleaned, invalid.block.start, invalid.block.end)
    return cleaned


def _build_fenced_block(block_type: str, block_body: str) -> str:
    normalized_type = str(block_type or "").strip().lower()
    normalized_body = str(block_body or "").strip()
    return f"```{normalized_type}\n{normalized_body}\n```"


def _extract_repaired_body(raw_model_text: str, expected_type: str) -> str | None:
    source = str(raw_model_text or "").strip()
    if not source:
        return None

    normalized_type = str(expected_type or "").strip().lower()
    extracted_blocks = extract_visual_blocks(source)
    if extracted_blocks:
        for block in extracted_blocks:
            if block.block_type == normalized_type:
                return str(block.content or "").strip()
        return None

    if "```" in source:
        return None

    return source


async def _validate_block_async(
    *,
    block_type: str,
    block_body: str,
    tier2_validator: Any,
    tier2_enabled: bool,
    tier2_fail_open: bool,
) -> ValidationResult:
    normalized_type = str(block_type or "").strip().lower()
    if normalized_type == "chartjson":
        return await validate_chartjson_async(
            block_body,
            tier2_validator=tier2_validator,
            tier2_enabled=tier2_enabled,
            tier2_fail_open=tier2_fail_open,
        )
    if normalized_type == "mermaid":
        return await validate_mermaid_async(
            block_body,
            tier2_validator=tier2_validator,
            tier2_enabled=tier2_enabled,
            tier2_fail_open=tier2_fail_open,
        )
    return ValidationResult(False, f"Unsupported visualization type: {normalized_type}")


async def drop_invalid_visualizations(
    section: ContentSection,
    *,
    tier2_validator: Any,
    tier2_enabled: bool,
    tier2_fail_open: bool,
) -> ContentSection:
    report = await validate_section_visualizations(
        section.content,
        tier2_validator=tier2_validator,
        tier2_enabled=tier2_enabled,
        tier2_fail_open=tier2_fail_open,
    )
    if not report.invalid_blocks:
        return section

    cleaned_content = _remove_invalid_spans(section.content, report.invalid_blocks)
    return ContentSection(
        section_title=section.section_title,
        content=cleaned_content,
        citations=list(section.citations or []),
    )


async def repair_section_visualizations(
    section: ContentSection,
    *,
    visual_repair_enabled: bool,
    visual_repair_max_retries: int,
    visual_repair_retry_timeout_seconds: float,
    model: Any,
    node_builder: Any,
    tier2_validator: Any,
    tier2_enabled: bool,
    tier2_fail_open: bool,
    run_config: dict[str, Any] | None = None,
) -> ContentSection:
    if not visual_repair_enabled:
        return await drop_invalid_visualizations(
            section,
            tier2_validator=tier2_validator,
            tier2_enabled=tier2_enabled,
            tier2_fail_open=tier2_fail_open,
        )

    working_content = str(section.content or "")
    citations = list(section.citations or [])
    section_title = str(section.section_title or "").strip() or "Untitled Section"
    initial_report = await validate_section_visualizations(
        working_content,
        tier2_validator=tier2_validator,
        tier2_enabled=tier2_enabled,
        tier2_fail_open=tier2_fail_open,
    )
    if not initial_report.invalid_blocks:
        return ContentSection(
            section_title=section_title,
            content=working_content,
            citations=citations,
        )

    repair_attempt_budget = max(0, int(visual_repair_max_retries))
    invalid_blocks_desc = sorted(
        initial_report.invalid_blocks,
        key=lambda item: item.block.start,
        reverse=True,
    )

    for invalid in invalid_blocks_desc:
        original_block = invalid.block
        repaired = False

        if repair_attempt_budget > 0:
            for attempt in range(1, repair_attempt_budget + 1):
                repair_prompt = node_builder.repair_visual_block_prompt(
                    block_type=original_block.block_type,
                    block_content=original_block.content,
                    invalid_reason=invalid.reason,
                )
                try:
                    repaired_message = await asyncio.wait_for(
                        model.ainvoke(repair_prompt, config=run_config),
                        timeout=visual_repair_retry_timeout_seconds,
                    )
                    candidate_text = message_text(repaired_message)
                    candidate_body = _extract_repaired_body(
                        candidate_text,
                        original_block.block_type,
                    )
                    if not candidate_body:
                        continue

                    candidate_validation = await _validate_block_async(
                        block_type=original_block.block_type,
                        block_body=candidate_body,
                        tier2_validator=tier2_validator,
                        tier2_enabled=tier2_enabled,
                        tier2_fail_open=tier2_fail_open,
                    )
                    if not candidate_validation.is_valid:
                        continue

                    working_content = _replace_span(
                        working_content,
                        original_block.start,
                        original_block.end,
                        _build_fenced_block(original_block.block_type, candidate_body),
                    )
                    repaired = True
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    print(
                        f"[graph] Visualization block repair attempt {attempt}/{repair_attempt_budget} "
                        f"failed for section '{section_title}' ({original_block.block_type}): {error}"
                    )

        if not repaired:
            working_content = _remove_span(
                working_content,
                original_block.start,
                original_block.end,
            )

    final_report = await validate_section_visualizations(
        working_content,
        tier2_validator=tier2_validator,
        tier2_enabled=tier2_enabled,
        tier2_fail_open=tier2_fail_open,
    )
    if final_report.invalid_blocks:
        working_content = _remove_invalid_spans(working_content, final_report.invalid_blocks)

    return ContentSection(
        section_title=section_title,
        content=working_content,
        citations=citations,
    )


async def resolve_repair_task(
    task: asyncio.Task[ContentSection],
    fallback_section: ContentSection,
    *,
    tier2_validator: Any,
    tier2_enabled: bool,
    tier2_fail_open: bool,
) -> ContentSection:
    try:
        return await task
    except asyncio.CancelledError:
        raise
    except Exception as error:
        print(
            f"[graph] Visualization repair task crashed for section "
            f"'{fallback_section.section_title}': {error}. Applying safe fallback."
        )
        return await drop_invalid_visualizations(
            fallback_section,
            tier2_validator=tier2_validator,
            tier2_enabled=tier2_enabled,
            tier2_fail_open=tier2_fail_open,
        )
