import json
import re
from dataclasses import dataclass, field
from typing import Any


FENCED_VISUAL_PATTERN = re.compile(
    r"```(?P<type>chartjson|mermaid)[ \t]*\r?\n(?P<body>[\s\S]*?)```",
    re.IGNORECASE,
)
FUNCTION_LIKE_PATTERN = re.compile(r"^\s*(?:function\s*\(|\(?\s*[\w$,\s]+\)?\s*=>)")
UNSAFE_MERMAID_PATTERN = re.compile(r"<script|onerror\s*=|onload\s*=|javascript:", re.IGNORECASE)
UNSAFE_KEYS = {"__proto__", "prototype", "constructor"}
UNQUOTED_LABEL_PATTERN = re.compile(r"\b[A-Za-z_][\w-]*\[(?!\")([^\]\n]+)\]")
RISKY_UNQUOTED_LABEL_PATTERN = re.compile(r"[/&()\\,:;…]|[^\x00-\x7F]")
TRAILING_LABEL_TYPO_PATTERN = re.compile(r"\][A-Za-z_][A-Za-z0-9_]*(?:\s|$)")


@dataclass(frozen=True)
class VisualBlock:
    block_type: str
    content: str
    raw: str
    start: int
    end: int


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reason: str | None = None


@dataclass(frozen=True)
class InvalidVisualBlock:
    block: VisualBlock
    reason: str


@dataclass
class SectionValidationReport:
    blocks: list[VisualBlock] = field(default_factory=list)
    invalid_blocks: list[InvalidVisualBlock] = field(default_factory=list)

    @property
    def has_invalid(self) -> bool:
        return bool(self.invalid_blocks)


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


def _has_unsafe_keys_or_values(input_value: Any) -> bool:
    if input_value is None:
        return False

    if isinstance(input_value, str):
        return bool(FUNCTION_LIKE_PATTERN.search(input_value))

    if isinstance(input_value, list):
        return any(_has_unsafe_keys_or_values(item) for item in input_value)

    if isinstance(input_value, dict):
        for key, value in input_value.items():
            if str(key) in UNSAFE_KEYS:
                return True
            if _has_unsafe_keys_or_values(value):
                return True
        return False

    return False


def validate_chartjson(block_text: str) -> ValidationResult:
    raw = str(block_text or "").strip()
    if not raw:
        return ValidationResult(False, "Empty chartjson block.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        return ValidationResult(False, f"Invalid chartjson JSON: {error.msg}.")

    if not isinstance(payload, dict):
        return ValidationResult(False, "chartjson payload root must be an object.")

    if _has_unsafe_keys_or_values(payload):
        return ValidationResult(
            False,
            "chartjson payload contains unsafe keys or function-like values.",
        )

    option = payload.get("option")
    if not isinstance(option, dict):
        return ValidationResult(False, 'chartjson payload must include an object field named "option".')

    title = payload.get("title")
    if title is not None and not isinstance(title, str):
        return ValidationResult(False, 'chartjson field "title" must be a string when provided.')

    caption = payload.get("caption")
    if caption is not None and not isinstance(caption, str):
        return ValidationResult(False, 'chartjson field "caption" must be a string when provided.')

    return ValidationResult(True, None)


def _has_balanced_delimiters(content: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    opening = set(pairs.values())
    stack: list[str] = []
    for char in content:
        if char in opening:
            stack.append(char)
            continue
        if char in pairs:
            if not stack or stack[-1] != pairs[char]:
                return False
            stack.pop()
    return len(stack) == 0


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

    if UNSAFE_MERMAID_PATTERN.search(source):
        return ValidationResult(False, "Mermaid block contains disallowed content.")

    if not _has_balanced_delimiters(source):
        return ValidationResult(False, "Mermaid block contains unbalanced delimiters.")

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
