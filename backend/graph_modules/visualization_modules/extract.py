from __future__ import annotations

import re

from .types import VisualBlock


FENCED_VISUAL_PATTERN = re.compile(
    r"```(?P<type>chartjson|mermaid)[ \t]*\r?\n(?P<body>[\s\S]*?)```",
    re.IGNORECASE,
)


def extract_visual_blocks(content: str) -> list[VisualBlock]:
    source = str(content or "")
    blocks: list[VisualBlock] = []
    for matched in FENCED_VISUAL_PATTERN.finditer(source):
        block_type = str(matched.group("type") or "").strip().lower()
        body = str(matched.group("body") or "").strip()
        blocks.append(
            VisualBlock(
                block_type=block_type,
                content=body,
                raw=str(matched.group(0) or ""),
                start=matched.start(),
                end=matched.end(),
            )
        )
    return blocks
