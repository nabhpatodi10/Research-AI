from __future__ import annotations

from types import SimpleNamespace

import pytest

from graph_modules.runtime_modules.equation_repair import repair_section_equations
from graph_modules.visualizations import EquationSpan, validate_equation
from structures import ContentSection


class _FakeNodeBuilder:
    def repair_equation_prompt(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        return "repair"


class _FakeRepairModel:
    async def ainvoke(self, prompt, config=None):  # noqa: ANN001
        _ = prompt, config
        return SimpleNamespace(content="")


def _span(style: str, expression: str) -> EquationSpan:
    return EquationSpan(style, expression, 0, len(expression), expression)


def test_tier1_rejects_unescaped_dollar_inside_equation() -> None:
    result = validate_equation(
        EquationSpan(
            "block_dollar",
            r"p_e =$0.13/\text{kWh}",
            0,
            24,
            r"$$p_e =$0.13/\text{kWh}$$",
        )
    )
    assert result.is_valid is False
    assert "unescaped '$'" in str(result.reason)


def test_tier1_rejects_unmatched_literal_delimiters() -> None:
    result = validate_equation(_span("inline_dollar", "156/kWh) = "))
    assert result.is_valid is False
    assert "Unmatched closing delimiter" in str(result.reason)


def test_tier1_rejects_dangling_operator_for_inline_equations() -> None:
    result = validate_equation(_span("inline_dollar", "x = "))
    assert result.is_valid is False
    assert "dangling operator" in str(result.reason)


def test_tier1_allows_escaped_dollar_inside_math() -> None:
    result = validate_equation(_span("inline_dollar", r"p = \$5"))
    assert result.is_valid is True


@pytest.mark.asyncio
async def test_equation_repair_downgrades_currency_false_positive_to_plain_text() -> None:
    repaired = await repair_section_equations(
        ContentSection(
            section_title="Costs",
            content="Battery premium (50 kWh × $156/kWh) = $7,800.",
            citations=[],
        ),
        equation_repair_max_retries=1,
        equation_repair_retry_timeout_seconds=0.1,
        model=_FakeRepairModel(),
        node_builder=_FakeNodeBuilder(),
        tier2_validator=None,
        tier2_enabled=False,
        tier2_fail_open=True,
        equation_max_chars=4096,
        run_config=None,
    )
    assert repaired.content == r"Battery premium (50 kWh × \$156/kWh) = \$7,800."


@pytest.mark.asyncio
async def test_equation_repair_fails_closed_when_tier2_expected_but_unavailable() -> None:
    repaired = await repair_section_equations(
        ContentSection(
            section_title="Prices",
            content=r"$$p_e =$0.13/\text{kWh}$$",
            citations=[],
        ),
        equation_repair_max_retries=1,
        equation_repair_retry_timeout_seconds=0.1,
        model=_FakeRepairModel(),
        node_builder=_FakeNodeBuilder(),
        tier2_validator=None,
        tier2_enabled=True,
        tier2_fail_open=True,
        equation_max_chars=4096,
        run_config=None,
    )
    assert repaired.content == r"`p_e =$0.13/\text{kWh}`"
