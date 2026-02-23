"""equation.py — Tier-1 structural validator for a single EquationSpan.

Comprehensive fast, pure-Python checks that detect obviously broken equations
before they are sent to the heavier Tier-2 KaTeX browser probe.

Checks (applied in order)
--------------------------
 1. Empty expression
 2. Expression too long (configurable *max_chars*)
 3. Unsafe / injection content  (<script, javascript:, data:)
 4. Disallowed macro-definition commands (\\newcommand, \\def, \\let, …)
 5. Null bytes and non-printable control characters
 6. Trailing lone backslash (incomplete control sequence)
 7. Bare ``%`` comment character (not ``\\%``)
 8. Inline-dollar spanning a real newline
 9. Nested ``$$`` inside an inline-dollar expression
10. Unbalanced curly braces ``{`` / ``}`` (stack — also catches premature close)
11. ``\\begin{env}`` with an empty environment name
12. ``\\begin`` / ``\\end`` environment mismatch — stack-based nesting check
13. Unbalanced ``\\left`` / ``\\right`` pairs (count-based)
14. Double superscript or double subscript at the same brace depth
15. ``\\frac``, ``\\binom``, ``\\stackrel`` etc. at end of expression without
    their required argument(s)
16. Illegal HTML / XML open tags injected into expression
"""

from __future__ import annotations

import re

from .types import EquationSpan, ValidationResult


# ── Compiled patterns ────────────────────────────────────────────────────────

# Unsafe injection patterns
_UNSAFE_RE = re.compile(r"<script|javascript:|data:\s*text/", re.IGNORECASE)

# Macro definition commands that KaTeX does not (safely) support
_MACRO_DEF_RE = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand|DeclareMathOperator"
    r"|def|edef|gdef|xdef|let|futurelet)\b",
)

# Control characters (ASCII 0x00-0x08, 0x0B-0x0C, 0x0E-0x1F, 0x7F) — excludes
# tab (0x09) and newline (0x0A) which are normal whitespace.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# \left / \right (not followed by a letter, so \leftarrow is excluded)
_LEFT_RE = re.compile(r"\\left(?![a-zA-Z])")
_RIGHT_RE = re.compile(r"\\right(?![a-zA-Z])")

# \begin{env} and \end{env}
_BEGIN_RE = re.compile(r"\\begin\{([^}]*)\}")
_END_RE = re.compile(r"\\end\{([^}]*)\}")

# Commands that require at least one mandatory braced argument.
# We check these are not followed by end-of-expression or another command.
_NEEDS_ARG_RE = re.compile(
    r"\\(?:frac|dfrac|tfrac|cfrac|binom|dbinom|tbinom|stackrel|overset|underset"
    r"|xrightarrow|xleftarrow|xleftrightarrow|xLeftarrow|xRightarrow|xlongequal"
    r"|overbrace|underbrace|sqrt|vec|hat|bar|dot|ddot|tilde|widetilde|widehat"
    r"|overline|underline|mathbb|mathbf|mathcal|mathfrak|mathit|mathrm|mathsf"
    r"|mathtt|boldsymbol|pmb|text|mbox|operatorname)\b"
)

# HTML / XML open tag injection: catches things like <div, <span, <img etc.
_HTML_TAG_RE = re.compile(r"<[a-zA-Z][a-zA-Z0-9]*[\s/>]")


# ── Internal helpers ─────────────────────────────────────────────────────────

def _check_brace_balance(expr: str) -> str | None:
    """Return an error message if ``{`` / ``}`` are unbalanced, else ``None``.

    Escaped braces (``\\{`` and ``\\}``) are treated as regular characters and
    do not affect the balance count.
    """
    depth = 0
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch == "\\":
            i += 2  # skip the escaped character entirely
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


def _check_env_nesting(expr: str) -> str | None:
    """Stack-based check that ``\\begin{env}``/``\\end{env}`` pairs are
    properly nested and perfectly matched.  Returns an error string or ``None``.
    """
    stack: list[str] = []
    for m in re.finditer(r"\\(begin|end)\{([^}]*)\}", expr):
        kind = m.group(1)   # "begin" or "end"
        env = m.group(2).strip()
        if not env:
            return "Empty environment name in \\begin{} or \\end{}."
        if kind == "begin":
            stack.append(env)
        else:  # end
            if not stack:
                return f"\\end{{{env}}} without a matching \\begin{{{env}}}."
            top = stack.pop()
            if top != env:
                return (
                    f"Mismatched environments: \\begin{{{top}}} closed by"
                    f" \\end{{{env}}}."
                )
    if stack:
        unclosed = ", ".join(f"\\begin{{{e}}}" for e in stack)
        return f"Unclosed environment(s): {unclosed}."
    return None


def _check_double_script(expr: str) -> str | None:
    """Detect double superscript (``x^a^b``) or double subscript (``x_a_b``)
    at the **same** brace depth.  Returns an error string or ``None``.

    Algorithm: scan characters; track brace depth.  At each depth maintain
    whether a ``^`` (superscript) or ``_`` (subscript) has been "opened and its
    argument consumed" since the last base token.  Consuming an argument means:
    advancing past a braced group ``{...}`` or a single non-space character.
    If the same operator is seen again at the same depth before the base is
    reset, that is a double-script error.
    """
    n = len(expr)
    i = 0
    # super_used[depth] and sub_used[depth] track whether a script has already
    # been placed at this depth without an intervening base token reset.
    super_used: dict[int, bool] = {}
    sub_used: dict[int, bool] = {}
    depth = 0

    def _consume_arg(pos: int) -> int:
        """Return the index after consuming one argument starting at *pos*."""
        # Skip leading whitespace
        while pos < n and expr[pos] in " \t\r\n":
            pos += 1
        if pos >= n:
            return pos
        if expr[pos] == "{":
            # Consume the braced group
            d = 0
            while pos < n:
                if expr[pos] == "\\" :
                    pos += 2
                    continue
                if expr[pos] == "{":
                    d += 1
                elif expr[pos] == "}":
                    d -= 1
                    if d == 0:
                        return pos + 1
                pos += 1
            return pos  # malformed, let brace check handle it
        elif expr[pos] == "\\":
            # Consume a control sequence
            pos += 1
            if pos < n and not expr[pos].isalpha():
                return pos + 1  # single-char control seq like \, \! etc.
            while pos < n and expr[pos].isalpha():
                pos += 1
            return pos
        else:
            return pos + 1

    while i < n:
        ch = expr[i]

        if ch == "\\":
            # Skip the control sequence name — it acts as a base token at this depth.
            i += 1
            if i < n and not expr[i].isalpha():
                i += 1  # \( \) \[ \] etc.
            else:
                while i < n and expr[i].isalpha():
                    i += 1
            # The control sequence is a base; reset script tracking at this depth.
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
            # Closing a group is itself a base reset at the enclosing depth.
            super_used[depth] = False
            sub_used[depth] = False
            i += 1
            continue

        if ch == "^":
            if super_used.get(depth):
                return "Double superscript: '^' applied twice to the same base."
            super_used[depth] = True
            # sub is reset because ^ changes the base context
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

        # Any other visible character is a base token; reset script tracking.
        super_used[depth] = False
        sub_used[depth] = False
        i += 1

    return None


def _check_needs_arg(expr: str) -> str | None:
    """Detect commands that require arguments but appear at the very end of the
    expression or are immediately followed by another command / closing brace
    without any argument.

    Returns an error string or ``None``.
    """
    for m in _NEEDS_ARG_RE.finditer(expr):
        cmd = m.group(0)
        rest = expr[m.end():].lstrip(" \t\r\n")
        if not rest:
            return f"{cmd} at end of expression without a required argument."
        # The next character must open an argument: either { or [ (optional arg
        # for sqrt/xrightarrow). Anything else is likely missing an argument,
        # but could also be `\vec x` (un-braced shorthand). KaTeX handles some
        # of those, so only flag if followed by another \command or end-of-expr.
        if rest[0] == "\\" and cmd in (
            r"\frac", r"\dfrac", r"\tfrac", r"\cfrac",
            r"\binom", r"\dbinom", r"\tbinom",
            r"\stackrel", r"\overset", r"\underset",
        ):
            return (
                f"{cmd} is followed by another command without its required"
                " argument(s)."
            )
    return None


# ── Public API ───────────────────────────────────────────────────────────────

def validate_equation(span: EquationSpan, *, max_chars: int = 4096) -> ValidationResult:
    """Return a :class:`ValidationResult` for the equation described by *span*.

    *max_chars* caps the expression length that Tier-1 will accept; expressions
    longer than this are returned as ``{"is_valid": False}``.  The default
    matches the ``visual_tier2_equation_max_chars`` setting default.
    """
    expr: str = span.expression

    # 1. Empty expression ────────────────────────────────────────────────────
    if not expr or not expr.strip():
        return ValidationResult(False, "Equation expression is empty.")

    # 2. Max character length ────────────────────────────────────────────────
    if len(expr) > int(max_chars):
        return ValidationResult(
            False,
            f"Equation expression is too long ({len(expr)} chars > {int(max_chars)}).",
        )

    # 3. Unsafe / injection content ──────────────────────────────────────────
    if _UNSAFE_RE.search(expr):
        return ValidationResult(False, "Equation contains potentially unsafe content.")

    # 4. Disallowed macro-definition commands ────────────────────────────────
    macro_m = _MACRO_DEF_RE.search(expr)
    if macro_m:
        return ValidationResult(
            False,
            f"Equation contains a disallowed macro command: {macro_m.group(0)!r}.",
        )

    # 5. Null bytes / invalid control characters ──────────────────────────────
    if _CONTROL_CHAR_RE.search(expr):
        return ValidationResult(
            False,
            "Equation contains null bytes or non-printable control characters.",
        )

    # 6. Trailing lone backslash (incomplete control sequence) ────────────────
    stripped = expr.rstrip()
    if stripped.endswith("\\") and not stripped.endswith("\\\\"):
        return ValidationResult(
            False,
            "Equation ends with an incomplete backslash sequence.",
        )

    # 7. Bare % comment character (not \%) ───────────────────────────────────
    # Walk through characters; a % not preceded by \ indicates a comment start,
    # which KaTeX does not support and treats as a parse error.
    bare_percent = False
    prev: str = ""
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

    # 8. Inline-dollar spanning a real newline ────────────────────────────────
    if span.delimiter_style == "inline_dollar" and "\n" in expr:
        return ValidationResult(
            False,
            "Inline-dollar equation spans a newline; use $$ or \\[...\\] for display math.",
        )

    # 9. Nested $$ inside an inline-dollar expression ─────────────────────────
    if span.delimiter_style == "inline_dollar" and "$$" in expr:
        return ValidationResult(
            False,
            "Inline-dollar expression contains '$$'; use $$ delimiters for display math.",
        )

    # 10. Unbalanced curly braces ─────────────────────────────────────────────
    brace_error = _check_brace_balance(expr)
    if brace_error:
        return ValidationResult(False, brace_error)

    # 11 & 12. \begin{env} / \end{env} nesting and matching ──────────────────
    env_error = _check_env_nesting(expr)
    if env_error:
        return ValidationResult(False, env_error)

    # 13. Unbalanced \left / \right ───────────────────────────────────────────
    lefts = len(_LEFT_RE.findall(expr))
    rights = len(_RIGHT_RE.findall(expr))
    if lefts != rights:
        return ValidationResult(
            False,
            f"Unmatched \\left/\\right pairs ({lefts} \\left vs {rights} \\right).",
        )

    # 14. Double superscript / subscript ──────────────────────────────────────
    script_error = _check_double_script(expr)
    if script_error:
        return ValidationResult(False, script_error)

    # 15. Commands missing required argument ──────────────────────────────────
    arg_error = _check_needs_arg(expr)
    if arg_error:
        return ValidationResult(False, arg_error)

    # 16. HTML / XML tag injection ────────────────────────────────────────────
    if _HTML_TAG_RE.search(expr):
        return ValidationResult(False, "Equation contains an HTML/XML tag.")

    return ValidationResult(True)
