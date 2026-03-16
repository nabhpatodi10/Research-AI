"""Tier-1 structural validator for a single EquationSpan.

This module applies fast, pure-Python checks before optional Tier-2 KaTeX
validation. It is intentionally conservative about malformed inline dollar
spans because currency/prose can otherwise be misparsed as math.
"""

from __future__ import annotations

import re

from .types import EquationSpan, ValidationResult


_UNSAFE_RE = re.compile(r"<script|javascript:|data:\s*text/", re.IGNORECASE)

_MACRO_DEF_RE = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand|DeclareMathOperator"
    r"|def|edef|gdef|xdef|let|futurelet)\b",
)

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_LEFT_RE = re.compile(r"\\left(?![a-zA-Z])")
_RIGHT_RE = re.compile(r"\\right(?![a-zA-Z])")

_NEEDS_ARG_RE = re.compile(
    r"\\(?:frac|dfrac|tfrac|cfrac|binom|dbinom|tbinom|stackrel|overset|underset"
    r"|xrightarrow|xleftarrow|xleftrightarrow|xLeftarrow|xRightarrow|xlongequal"
    r"|overbrace|underbrace|sqrt|vec|hat|bar|dot|ddot|tilde|widetilde|widehat"
    r"|overline|underline|mathbb|mathbf|mathcal|mathfrak|mathit|mathrm|mathsf"
    r"|mathtt|boldsymbol|pmb|text|mbox|operatorname)\b"
)

_HTML_TAG_RE = re.compile(r"<[a-zA-Z][a-zA-Z0-9]*[\s/>]")

_DANGLING_OPERATOR_RE = re.compile(
    r"(?:"
    r"[=+\-*/<>]"
    r"|\\(?:approx|sim|simeq|neq|ne|le|leq|ge|geq|to|rightarrow|leftarrow|leftrightarrow"
    r"|mapsto|in|notin|subset|subseteq|supset|supseteq|times|cdot|pm|mp)"
    r")\s*$"
)


def _is_escaped(text: str, index: int) -> bool:
    """Return True when text[index] is escaped by an odd number of backslashes."""
    backslash_count = 0
    probe = index - 1
    while probe >= 0 and text[probe] == "\\":
        backslash_count += 1
        probe -= 1
    return (backslash_count % 2) == 1


def _check_brace_balance(expr: str) -> str | None:
    depth = 0
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return "Unmatched closing brace '}' (no matching '{')."
        i += 1
    if depth > 0:
        return f"Unclosed brace group ({depth} '{{' without matching '}}')."
    return None


def _check_unescaped_dollar(expr: str) -> str | None:
    for index, ch in enumerate(expr):
        if ch == "$" and not _is_escaped(expr, index):
            return "Equation contains an unescaped '$' inside the expression body."
    return None


def _check_literal_delimiter_balance(expr: str) -> str | None:
    stack: list[str] = []
    pairs = {
        ")": "(",
        "]": "[",
    }
    for index, ch in enumerate(expr):
        if ch not in "()[]":
            continue
        if _is_escaped(expr, index):
            continue
        if ch in "([":
            stack.append(ch)
            continue
        if not stack:
            return f"Unmatched closing delimiter '{ch}' in equation."
        opener = stack.pop()
        if pairs[ch] != opener:
            return f"Mismatched literal delimiters '{opener}' and '{ch}' in equation."
    if stack:
        return f"Unclosed literal delimiter '{stack[-1]}' in equation."
    return None


def _check_env_nesting(expr: str) -> str | None:
    stack: list[str] = []
    for match in re.finditer(r"\\(begin|end)\{([^}]*)\}", expr):
        kind = match.group(1)
        env = match.group(2).strip()
        if not env:
            return "Empty environment name in \\begin{} or \\end{}."
        if kind == "begin":
            stack.append(env)
            continue
        if not stack:
            return f"\\end{{{env}}} without a matching \\begin{{{env}}}."
        opener = stack.pop()
        if opener != env:
            return f"Mismatched environments: \\begin{{{opener}}} closed by \\end{{{env}}}."
    if stack:
        unclosed = ", ".join(f"\\begin{{{env}}}" for env in stack)
        return f"Unclosed environment(s): {unclosed}."
    return None


def _check_double_script(expr: str) -> str | None:
    n = len(expr)
    i = 0
    super_used: dict[int, bool] = {}
    sub_used: dict[int, bool] = {}
    depth = 0

    def _consume_arg(pos: int) -> int:
        while pos < n and expr[pos] in " \t\r\n":
            pos += 1
        if pos >= n:
            return pos
        if expr[pos] == "{":
            brace_depth = 0
            while pos < n:
                if expr[pos] == "\\":
                    pos += 2
                    continue
                if expr[pos] == "{":
                    brace_depth += 1
                elif expr[pos] == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        return pos + 1
                pos += 1
            return pos
        if expr[pos] == "\\":
            pos += 1
            if pos < n and not expr[pos].isalpha():
                return pos + 1
            while pos < n and expr[pos].isalpha():
                pos += 1
            return pos
        return pos + 1

    while i < n:
        ch = expr[i]
        if ch == "\\":
            i += 1
            if i < n and not expr[i].isalpha():
                i += 1
            else:
                while i < n and expr[i].isalpha():
                    i += 1
            super_used[depth] = False
            sub_used[depth] = False
            continue
        if ch == "{":
            depth += 1
            super_used[depth] = False
            sub_used[depth] = False
            i += 1
            continue
        if ch == "}":
            super_used.pop(depth, None)
            sub_used.pop(depth, None)
            depth = max(0, depth - 1)
            super_used[depth] = False
            sub_used[depth] = False
            i += 1
            continue
        if ch == "^":
            if super_used.get(depth):
                return "Double superscript: '^' applied twice to the same base."
            super_used[depth] = True
            sub_used[depth] = False
            i = _consume_arg(i + 1)
            continue
        if ch == "_":
            if sub_used.get(depth):
                return "Double subscript: '_' applied twice to the same base."
            sub_used[depth] = True
            super_used[depth] = False
            i = _consume_arg(i + 1)
            continue
        if ch in " \t\r\n":
            i += 1
            continue
        super_used[depth] = False
        sub_used[depth] = False
        i += 1

    return None


def _check_needs_arg(expr: str) -> str | None:
    for match in _NEEDS_ARG_RE.finditer(expr):
        cmd = match.group(0)
        rest = expr[match.end() :].lstrip(" \t\r\n")
        if not rest:
            return f"{cmd} at end of expression without a required argument."
        if rest[0] == "\\" and cmd in (
            r"\frac",
            r"\dfrac",
            r"\tfrac",
            r"\cfrac",
            r"\binom",
            r"\dbinom",
            r"\tbinom",
            r"\stackrel",
            r"\overset",
            r"\underset",
        ):
            return f"{cmd} is followed by another command without its required argument(s)."
    return None


def _check_dangling_operator(expr: str) -> str | None:
    stripped = expr.rstrip()
    if stripped and _DANGLING_OPERATOR_RE.search(stripped):
        return "Equation ends with a dangling operator or relation token."
    return None


def validate_equation(span: EquationSpan, *, max_chars: int = 4096) -> ValidationResult:
    """Return a ValidationResult for the equation described by span."""
    expr = str(span.expression or "")

    if not expr.strip():
        return ValidationResult(False, "Equation expression is empty.")

    if len(expr) > int(max_chars):
        return ValidationResult(
            False,
            f"Equation expression is too long ({len(expr)} chars > {int(max_chars)}).",
        )

    if _UNSAFE_RE.search(expr):
        return ValidationResult(False, "Equation contains potentially unsafe content.")

    macro_match = _MACRO_DEF_RE.search(expr)
    if macro_match:
        return ValidationResult(
            False,
            f"Equation contains a disallowed macro command: {macro_match.group(0)!r}.",
        )

    if _CONTROL_CHAR_RE.search(expr):
        return ValidationResult(
            False,
            "Equation contains null bytes or non-printable control characters.",
        )

    stripped = expr.rstrip()
    if stripped.endswith("\\") and not stripped.endswith("\\\\"):
        return ValidationResult(
            False,
            "Equation ends with an incomplete backslash sequence.",
        )

    bare_percent = False
    prev = ""
    for ch in expr:
        if ch == "%" and prev != "\\":
            bare_percent = True
            break
        prev = ch
    if bare_percent:
        return ValidationResult(
            False,
            "Equation contains a bare '%' (comment character). Use '\\%' for a literal percent sign.",
        )

    if span.delimiter_style == "inline_dollar" and "\n" in expr:
        return ValidationResult(
            False,
            "Inline-dollar equation spans a newline; use $$ or \\[...\\] for display math.",
        )

    if span.delimiter_style == "inline_dollar" and "$$" in expr:
        return ValidationResult(
            False,
            "Inline-dollar expression contains '$$'; use $$ delimiters for display math.",
        )

    brace_error = _check_brace_balance(expr)
    if brace_error:
        return ValidationResult(False, brace_error)

    dollar_error = _check_unescaped_dollar(expr)
    if dollar_error:
        return ValidationResult(False, dollar_error)

    literal_delimiter_error = _check_literal_delimiter_balance(expr)
    if literal_delimiter_error:
        return ValidationResult(False, literal_delimiter_error)

    env_error = _check_env_nesting(expr)
    if env_error:
        return ValidationResult(False, env_error)

    lefts = len(_LEFT_RE.findall(expr))
    rights = len(_RIGHT_RE.findall(expr))
    if lefts != rights:
        return ValidationResult(
            False,
            f"Unmatched \\left/\\right pairs ({lefts} \\left vs {rights} \\right).",
        )

    script_error = _check_double_script(expr)
    if script_error:
        return ValidationResult(False, script_error)

    arg_error = _check_needs_arg(expr)
    if arg_error:
        return ValidationResult(False, arg_error)

    if span.delimiter_style in ("inline_dollar", "inline_paren"):
        dangling_operator_error = _check_dangling_operator(expr)
        if dangling_operator_error:
            return ValidationResult(False, dangling_operator_error)

    if _HTML_TAG_RE.search(expr):
        return ValidationResult(False, "Equation contains an HTML/XML tag.")

    return ValidationResult(True)
