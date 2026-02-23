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
