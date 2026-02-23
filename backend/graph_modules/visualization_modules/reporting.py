from __future__ import annotations

import re

from .types import InvalidVisualBlock, SectionValidationReport


def drop_invalid_blocks(content: str, invalid_blocks: list[InvalidVisualBlock]) -> str:
    source = str(content or "")
    if not invalid_blocks:
        return source

    sorted_blocks = sorted(invalid_blocks, key=lambda item: item.block.start)
    parts: list[str] = []
    cursor = 0
    for invalid in sorted_blocks:
        start = max(0, invalid.block.start)
        end = min(len(source), invalid.block.end)
        if start < cursor:
            continue
        parts.append(source[cursor:start])
        cursor = end
    parts.append(source[cursor:])
    cleaned = "".join(parts)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def format_invalid_visual_report(report: SectionValidationReport) -> str:
    if not report.invalid_blocks:
        return "No invalid visualization blocks found."

    rows: list[str] = []
    for index, invalid in enumerate(report.invalid_blocks, start=1):
        snippet = re.sub(r"\s+", " ", invalid.block.content).strip()
        if len(snippet) > 220:
            snippet = snippet[:220] + "..."
        rows.append(
            f"{index}. type={invalid.block.block_type}; reason={invalid.reason}; snippet={snippet}"
        )
    return "\n".join(rows)
