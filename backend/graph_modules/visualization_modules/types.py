from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class EquationSpan:
    # delimiter_style: "inline_dollar" | "block_dollar" | "inline_paren" | "block_bracket"
    delimiter_style: str
    expression: str
    start: int   # byte offset of opening delimiter in source
    end: int     # byte offset just after closing delimiter
    full_match: str  # complete matched text including delimiters


@dataclass(frozen=True)
class InvalidEquationSpan:
    span: EquationSpan
    reason: str


@dataclass
class SectionEquationReport:
    spans: list[EquationSpan] = field(default_factory=list)
    invalid_spans: list[InvalidEquationSpan] = field(default_factory=list)

    @property
    def has_invalid(self) -> bool:
        return bool(self.invalid_spans)
