from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from .chartjson import validate_chartjson
from .extract import extract_visual_blocks
from .mermaid import validate_mermaid
from .types import InvalidVisualBlock, SectionValidationReport, ValidationResult, VisualBlock


if TYPE_CHECKING:
    from ..visual_tier2 import PlaywrightVisualTier2Validator


async def validate_mermaid_async(
    block_text: str,
    *,
    tier2_validator: "PlaywrightVisualTier2Validator | None" = None,
    tier2_enabled: bool = False,
    tier2_fail_open: bool = True,
) -> ValidationResult:
    primary_result = validate_mermaid(block_text)
    if not primary_result.is_valid:
        return primary_result

    if not tier2_enabled or tier2_validator is None:
        return primary_result

    status, reason = await tier2_validator.validate_mermaid(str(block_text or ""))
    if status == "valid":
        return primary_result

    if status == "invalid":
        return ValidationResult(False, reason or "Mermaid failed Tier-2 validation.")

    if tier2_fail_open:
        return primary_result
    return ValidationResult(
        False,
        reason or "Mermaid Tier-2 validator is unavailable.",
    )


async def validate_chartjson_async(
    block_text: str,
    *,
    tier2_validator: "PlaywrightVisualTier2Validator | None" = None,
    tier2_enabled: bool = False,
    tier2_fail_open: bool = True,
) -> ValidationResult:
    primary_result = validate_chartjson(block_text)
    if not primary_result.is_valid:
        return primary_result

    if not tier2_enabled or tier2_validator is None:
        return primary_result

    try:
        payload = json.loads(str(block_text or "").strip())
    except json.JSONDecodeError:
        return ValidationResult(False, "Invalid chartjson JSON.")

    option = payload.get("option")
    if not isinstance(option, dict):
        return ValidationResult(False, 'chartjson payload must include an object field named "option".')

    status, reason = await tier2_validator.validate_chartjson_option(option)
    if status == "valid":
        return primary_result

    if status == "invalid":
        return ValidationResult(False, reason or "chartjson failed Tier-2 validation.")

    if tier2_fail_open:
        return primary_result
    return ValidationResult(False, reason or "chartjson Tier-2 validator is unavailable.")


def validate_section_visualizations(content: str) -> SectionValidationReport:
    blocks = extract_visual_blocks(content)
    invalid: list[InvalidVisualBlock] = []

    for block in blocks:
        if block.block_type == "chartjson":
            result = validate_chartjson(block.content)
        elif block.block_type == "mermaid":
            result = validate_mermaid(block.content)
        else:
            continue

        if not result.is_valid:
            invalid.append(InvalidVisualBlock(block=block, reason=str(result.reason or "Invalid block.")))

    return SectionValidationReport(blocks=blocks, invalid_blocks=invalid)


async def validate_section_visualizations_async(
    content: str,
    *,
    tier2_validator: "PlaywrightVisualTier2Validator | None" = None,
    tier2_enabled: bool = False,
    tier2_fail_open: bool = True,
) -> SectionValidationReport:
    blocks = extract_visual_blocks(content)
    invalid: list[InvalidVisualBlock] = []

    jobs: list[tuple[VisualBlock, asyncio.Task[ValidationResult]]] = []
    for block in blocks:
        if block.block_type == "chartjson":
            jobs.append(
                (
                    block,
                    asyncio.create_task(
                        validate_chartjson_async(
                            block.content,
                            tier2_validator=tier2_validator,
                            tier2_enabled=tier2_enabled,
                            tier2_fail_open=tier2_fail_open,
                        )
                    ),
                )
            )
            continue
        if block.block_type == "mermaid":
            jobs.append(
                (
                    block,
                    asyncio.create_task(
                        validate_mermaid_async(
                            block.content,
                            tier2_validator=tier2_validator,
                            tier2_enabled=tier2_enabled,
                            tier2_fail_open=tier2_fail_open,
                        )
                    ),
                )
            )

    for block, task in jobs:
        try:
            result = await task
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if tier2_fail_open:
                result = ValidationResult(True, None)
            else:
                result = ValidationResult(
                    False,
                    f"Visualization Tier-2 validator crashed: {error}",
                )

        if not result.is_valid:
            invalid.append(
                InvalidVisualBlock(
                    block=block,
                    reason=str(result.reason or "Invalid block."),
                )
            )

    return SectionValidationReport(blocks=blocks, invalid_blocks=invalid)
