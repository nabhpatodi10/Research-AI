"""equation_repair.py — LLM repair loop for invalid equation spans.

Mirrors ``visual_repair.py`` in structure: validates all spans, iterates over
invalid spans back-to-front, attempts LLM repair up to *equation_repair_max_retries*
times, and falls back to replacing the broken equation with an inline code span
(`` `expression` ``) so the surrounding prose is preserved.
"""

from __future__ import annotations

import asyncio
from typing import Any

from structures import ContentSection

from ..helpers import message_text
from ..visualizations import (
    EquationSpan,
    InvalidEquationSpan,
    SectionEquationReport,
    ValidationResult,
    extract_equation_spans,
    validate_equation_async,
)


# ── Internal helpers ─────────────────────────────────────────────────────────

def _replace_span(source: str, start: int, end: int, replacement: str) -> str:
    normalized = str(source or "")
    safe_start = max(0, min(len(normalized), int(start)))
    safe_end = max(safe_start, min(len(normalized), int(end)))
    return normalized[:safe_start] + str(replacement) + normalized[safe_end:]


def _code_span_fallback(expression: str) -> str:
    """Replace an invalid equation with a safe inline code span."""
    # Escape any back-ticks inside the expression to avoid breaking the code span.
    escaped = str(expression or "").replace("`", "'")
    return f"`{escaped}`"


def _build_delimited_equation(delimiter_style: str, expression: str) -> str:
    """Wrap *expression* back in its original delimiter style."""
    style = str(delimiter_style or "").strip().lower()
    expr = str(expression or "")
    if style == "block_dollar":
        return f"$${expr}$$"
    if style == "block_bracket":
        return f"\\[{expr}\\]"
    if style == "inline_paren":
        return f"\\({expr}\\)"
    # Default: inline_dollar
    return f"${expr}$"


async def _validate_all_spans(
    content: str,
    *,
    tier2_validator: Any,
    tier2_enabled: bool,
    tier2_fail_open: bool,
    equation_max_chars: int,
) -> SectionEquationReport:
    """Extract and validate every equation span in *content* concurrently."""
    spans = extract_equation_spans(content)
    if not spans:
        return SectionEquationReport()

    tasks = [
        validate_equation_async(
            span,
            tier2_validator=tier2_validator,
            tier2_enabled=tier2_enabled,
            tier2_fail_open=tier2_fail_open,
            equation_max_chars=equation_max_chars,
        )
        for span in spans
    ]
    results: list[ValidationResult] = await asyncio.gather(*tasks)

    report = SectionEquationReport(spans=list(spans))
    for span, result in zip(spans, results):
        if not result.is_valid:
            report.invalid_spans.append(
                InvalidEquationSpan(span=span, reason=str(result.reason or ""))
            )
    return report


# ── Public API ───────────────────────────────────────────────────────────────

async def repair_section_equations(
    section: ContentSection,
    *,
    equation_repair_max_retries: int,
    equation_repair_retry_timeout_seconds: float,
    model: Any,
    node_builder: Any,
    tier2_validator: Any,
    tier2_enabled: bool,
    tier2_fail_open: bool,
    equation_max_chars: int = 4096,
    run_config: dict[str, Any] | None = None,
) -> ContentSection:
    """Repair invalid equation spans inside *section*.

    For each invalid span (processed back-to-front to preserve offsets):

    * Attempt LLM repair up to *equation_repair_max_retries* times.
    * If a valid repair is produced, splice it back via :func:`_replace_span`.
    * If all attempts fail, replace the equation with `` `raw_expression` `` so
      surrounding prose is never lost.

    Returns a new :class:`ContentSection` with the repaired content.
    """
    working_content = str(section.content or "")
    citations = list(section.citations or [])
    section_title = str(section.section_title or "").strip() or "Untitled Section"

    initial_report = await _validate_all_spans(
        working_content,
        tier2_validator=tier2_validator,
        tier2_enabled=tier2_enabled,
        tier2_fail_open=tier2_fail_open,
        equation_max_chars=equation_max_chars,
    )

    if not initial_report.invalid_spans:
        return ContentSection(
            section_title=section_title,
            content=working_content,
            citations=citations,
        )

    repair_attempt_budget = max(0, int(equation_repair_max_retries))

    # Process invalid spans back-to-front so that earlier offsets are
    # unaffected by replacements at later positions.
    invalid_desc = sorted(
        initial_report.invalid_spans,
        key=lambda item: item.span.start,
        reverse=True,
    )

    for invalid in invalid_desc:
        original_span = invalid.span
        repaired = False

        if repair_attempt_budget > 0:
            for attempt in range(1, repair_attempt_budget + 1):
                repair_prompt = node_builder.repair_equation_prompt(
                    delimiter_style=original_span.delimiter_style,
                    expression=original_span.expression,
                    invalid_reason=invalid.reason,
                )
                try:
                    repaired_message = await asyncio.wait_for(
                        model.ainvoke(repair_prompt, config=run_config),
                        timeout=equation_repair_retry_timeout_seconds,
                    )
                    candidate_text = str(message_text(repaired_message) or "").strip()
                    if not candidate_text:
                        continue

                    # Validate the candidate expression (Tier-1, plus optional Tier-2).
                    candidate_span = EquationSpan(
                        delimiter_style=original_span.delimiter_style,
                        expression=candidate_text,
                        start=0,
                        end=len(candidate_text),
                        full_match=candidate_text,
                    )
                    candidate_result = await validate_equation_async(
                        candidate_span,
                        tier2_validator=tier2_validator,
                        tier2_enabled=tier2_enabled,
                        tier2_fail_open=tier2_fail_open,
                        equation_max_chars=equation_max_chars,
                    )
                    if not candidate_result.is_valid:
                        continue

                    candidate_replacement = _build_delimited_equation(
                        original_span.delimiter_style,
                        candidate_text,
                    )
                    working_content = _replace_span(
                        working_content,
                        original_span.start,
                        original_span.end,
                        candidate_replacement,
                    )
                    repaired = True
                    break

                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    print(
                        f"[graph] Equation repair attempt {attempt}/{repair_attempt_budget} "
                        f"failed for section '{section_title}' "
                        f"({original_span.delimiter_style}): {error}"
                    )

        if not repaired:
            # Fall back: replace broken equation with inline code span so prose
            # is never silently deleted.
            working_content = _replace_span(
                working_content,
                original_span.start,
                original_span.end,
                _code_span_fallback(original_span.expression),
            )

    return ContentSection(
        section_title=section_title,
        content=working_content,
        citations=citations,
    )


async def resolve_equation_repair_task(
    task: asyncio.Task[ContentSection],
    fallback_section: ContentSection,
) -> ContentSection:
    """Await *task* and return its result.  On crash, log a warning and return
    *fallback_section* unchanged (unlike visual repair, equations are never
    deleted silently — the fallback is already the unmodified section).
    """
    try:
        return await task
    except asyncio.CancelledError:
        raise
    except Exception as error:
        print(
            f"[graph] Equation repair task crashed for section "
            f"'{fallback_section.section_title}': {error}. "
            "Returning unrepaired section."
        )
        return fallback_section
