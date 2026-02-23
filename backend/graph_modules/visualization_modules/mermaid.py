from __future__ import annotations

import re

from .types import ValidationResult


UNSAFE_MERMAID_PATTERN = re.compile(r"<script|onerror\s*=|onload\s*=|javascript:", re.IGNORECASE)
UNQUOTED_LABEL_PATTERN = re.compile(r"\b[A-Za-z_][\w-]*\[(?!\")([^\]\n]+)\]")
RISKY_UNQUOTED_LABEL_PATTERN = re.compile(r"[/&()\\,:;]|[^\x00-\x7F]")
TRAILING_LABEL_TYPO_PATTERN = re.compile(r"[\]\)\}][A-Za-z_][A-Za-z0-9_]*(?:\s|$)")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
MERMAID_HEADER_PATTERN = re.compile(
    r"^\s*(?:"
    r"flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|"
    r"journey|gantt|pie(?:\s+showData)?|mindmap|timeline|gitGraph|quadrantChart|"
    r"requirementDiagram|sankey-beta|xychart-beta|block-beta|architecture(?:-beta)?|packet-beta"
    r")\b",
    re.IGNORECASE,
)
MALFORMED_ARROW_PATTERN = re.compile(r"-/->|--/>|-/-->|<-/->|<-/--")
EDGE_ARROW_TOKEN_PATTERN = re.compile(
    r"-->|<--|-\.->|<-\.-|==>|<==|--x|x--|--o|o--|---",
    re.IGNORECASE,
)


def _has_balanced_delimiters(content: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    opening = set(pairs.values())
    stack: list[str] = []
    in_double_quote = False
    escaped = False

    for char in content:
        if in_double_quote:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_double_quote = False
            continue

        if char == '"':
            in_double_quote = True
            continue

        if char in opening:
            stack.append(char)
            continue
        if char in pairs:
            if not stack or stack[-1] != pairs[char]:
                return False
            stack.pop()

    return len(stack) == 0 and not in_double_quote


def _first_mermaid_content_line(content: str) -> str:
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%%"):
            continue
        return line
    return ""


def _find_unbalanced_double_quote_line(content: str) -> int | None:
    for index, raw_line in enumerate(str(content or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("%%"):
            continue

        quote_count = 0
        escaped = False
        for char in raw_line:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                quote_count += 1

        if quote_count % 2 != 0:
            return index

    return None


def _has_label_newlines(content: str) -> bool:
    """Return True if any double-quoted label string contains a literal newline.

    A real newline inside a quoted mermaid label (e.g. ``["line1\nline2"]``) terminates
    the lexer token and causes a parse error.  The correct multiline syntax is ``<br/>``.
    """
    in_double_quote = False
    escaped = False
    for char in str(content or ""):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_double_quote = not in_double_quote
            continue
        if in_double_quote and char in ("\n", "\r"):
            return True
    return False


def _has_unbalanced_edge_label_pipes(content: str) -> bool:
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%%"):
            continue
        if "|" not in line:
            continue
        if not EDGE_ARROW_TOKEN_PATTERN.search(line):
            continue
        if line.count("|") % 2 != 0:
            return True
    return False


def _find_unquoted_risky_mermaid_label(content: str) -> str | None:
    for matched in UNQUOTED_LABEL_PATTERN.finditer(content):
        label = str(matched.group(1) or "").strip()
        if not label:
            continue
        if RISKY_UNQUOTED_LABEL_PATTERN.search(label):
            return label
    return None


def validate_mermaid(block_text: str) -> ValidationResult:
    source = str(block_text or "").strip()
    if not source:
        return ValidationResult(False, "Empty mermaid block.")

    if "```" in source:
        return ValidationResult(False, "Mermaid block contains nested markdown fences.")

    if CONTROL_CHAR_PATTERN.search(source):
        return ValidationResult(False, "Mermaid block contains disallowed control characters.")

    if _has_label_newlines(source):
        return ValidationResult(
            False,
            "Mermaid label contains embedded newlines; use <br/> for multi-line labels.",
        )

    if UNSAFE_MERMAID_PATTERN.search(source):
        return ValidationResult(False, "Mermaid block contains disallowed content.")

    first_line = _first_mermaid_content_line(source)
    if not first_line:
        return ValidationResult(False, "Mermaid block has no diagram content.")
    if not MERMAID_HEADER_PATTERN.search(first_line):
        return ValidationResult(False, "Mermaid block is missing a valid diagram header.")

    quote_error_line = _find_unbalanced_double_quote_line(source)
    if quote_error_line is not None:
        return ValidationResult(
            False,
            f"Mermaid block has unbalanced double quotes on line {quote_error_line}.",
        )

    if not _has_balanced_delimiters(source):
        return ValidationResult(False, "Mermaid block contains unbalanced delimiters.")

    if MALFORMED_ARROW_PATTERN.search(source):
        return ValidationResult(False, "Mermaid block contains malformed edge syntax.")

    if _has_unbalanced_edge_label_pipes(source):
        return ValidationResult(False, "Mermaid edge labels contain unbalanced | pipes.")

    risky_label = _find_unquoted_risky_mermaid_label(source)
    if risky_label:
        return ValidationResult(
            False,
            f'Mermaid label "{risky_label}" should be quoted as nodeId["Label"].',
        )

    if TRAILING_LABEL_TYPO_PATTERN.search(source):
        return ValidationResult(
            False,
            "Mermaid block contains an unexpected token after a node label.",
        )

    return ValidationResult(True, None)
