"""extract_equations.py — scan section content for equation spans.

Scans a markdown string and returns every equation span found, in source order,
while skipping code fences (```...```) and inline code (`...`).

Supported delimiter styles
--------------------------
block_dollar   :  $$...$$
inline_dollar  :  $...$  (must not span a real newline)
block_bracket  :  \\[...\\]
inline_paren   :  \\(...\\)
"""

from __future__ import annotations

import re

from .types import EquationSpan


# Matches triple-backtick fenced code blocks (greedy-off, dotall).
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")

# Matches single-backtick inline code (no nested backticks, allows spaces).
_INLINE_CODE_RE = re.compile(r"`[^`]+`")


def _build_masked(text: str) -> str:
    """Return a char-for-char copy of *text* where every character that sits
    inside a code fence or inline-code span is replaced with the null byte
    ``\\x00`` (kept for non-newline positions) so that delimiter searches on the
    masked string cannot accidentally match inside code spans.

    Newlines inside code fences are preserved so that the inline-dollar
    newline guard still works correctly on the masked text.
    """
    masked = list(text)

    # First pass: triple-backtick fences (takes priority).
    fence_ranges: list[tuple[int, int]] = []
    for m in _CODE_FENCE_RE.finditer(text):
        fence_ranges.append((m.start(), m.end()))
        for k in range(m.start(), m.end()):
            if text[k] != "\n":
                masked[k] = "\x00"

    # Second pass: inline code spans that are NOT already inside a fence.
    def _in_fence(pos: int) -> bool:
        for s, e in fence_ranges:
            if s <= pos < e:
                return True
        return False

    for m in _INLINE_CODE_RE.finditer(text):
        if not _in_fence(m.start()):
            for k in range(m.start(), m.end()):
                if text[k] != "\n":
                    masked[k] = "\x00"

    return "".join(masked)


def extract_equation_spans(source: str) -> list[EquationSpan]:
    """Return all :class:`EquationSpan` objects found in *source*, in order of
    their appearance.  Code fences and inline-code spans are silently skipped.
    """
    text = str(source or "")
    if not text:
        return []

    masked = _build_masked(text)
    n = len(masked)
    spans: list[EquationSpan] = []
    i = 0

    while i < n:
        # Skip masked (code-span) positions.
        if masked[i] == "\x00":
            i += 1
            continue

        # ── block_dollar  $$...$$  ──────────────────────────────────────────
        # Must be tested before single-$ to avoid eating one $ of a $$ pair.
        if masked[i : i + 2] == "$$":
            close = masked.find("$$", i + 2)
            if close != -1:
                end = close + 2
                spans.append(
                    EquationSpan(
                        delimiter_style="block_dollar",
                        expression=text[i + 2 : close],
                        start=i,
                        end=end,
                        full_match=text[i:end],
                    )
                )
                i = end
                continue

        # ── inline_dollar  $...$  (no real newline allowed) ─────────────────
        if masked[i] == "$":
            j = i + 1
            found_close = -1
            while j < n:
                ch = masked[j]
                if ch == "\n":
                    # Real newline in source — inline dollar cannot cross it.
                    break
                if ch == "\x00":
                    j += 1
                    continue
                if ch == "$":
                    found_close = j
                    break
                j += 1
            if found_close != -1:
                end = found_close + 1
                spans.append(
                    EquationSpan(
                        delimiter_style="inline_dollar",
                        expression=text[i + 1 : found_close],
                        start=i,
                        end=end,
                        full_match=text[i:end],
                    )
                )
                i = end
                continue

        # ── block_bracket  \[...\]  ─────────────────────────────────────────
        if masked[i : i + 2] == "\\[":
            close = masked.find("\\]", i + 2)
            if close != -1:
                end = close + 2
                spans.append(
                    EquationSpan(
                        delimiter_style="block_bracket",
                        expression=text[i + 2 : close],
                        start=i,
                        end=end,
                        full_match=text[i:end],
                    )
                )
                i = end
                continue

        # ── inline_paren  \(...\)  ──────────────────────────────────────────
        if masked[i : i + 2] == "\\(":
            close = masked.find("\\)", i + 2)
            if close != -1:
                end = close + 2
                spans.append(
                    EquationSpan(
                        delimiter_style="inline_paren",
                        expression=text[i + 2 : close],
                        start=i,
                        end=end,
                        full_match=text[i:end],
                    )
                )
                i = end
                continue

        i += 1

    return spans
