const INLINE_EXPLICIT_MATH_RE = /\\\((.+?)\\\)/gs;
const EXPLICIT_DISPLAY_BLOCK_RE = /\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$/g;
const LEGACY_NESTED_INLINE_PAREN_RE = /\$\\\(([\s\S]*?)\\\)\$/g;
const LEGACY_NESTED_DISPLAY_PAREN_RE = /\$\$\\\(([\s\S]*?)\\\)\$\$/g;
const LEGACY_NESTED_INLINE_BRACKET_RE = /\$\\\[([\s\S]*?)\\\]\$/g;
const LEGACY_NESTED_DISPLAY_BRACKET_RE = /\$\$\\\[([\s\S]*?)\\\]\$\$/g;

const DANGLING_OPERATOR_RE =
  /(?:[=+\-*/<>]|\\(?:approx|sim|simeq|neq|ne|le|leq|ge|geq|to|rightarrow|leftarrow|leftrightarrow|mapsto|in|notin|subset|subseteq|supset|supseteq|times|cdot|pm|mp))\s*$/;

const MATH_SIGNAL_RE =
  /[\\^_=+\-*/<>]|\\(?:frac|sqrt|sum|int|cdot|times|alpha|beta|gamma|theta|pi|text|mathrm|mathbf|mathbb)\b/;

const STANDALONE_BRACKET_LATEX_RE =
  /^(\s*(?:[-*+]\s+|\d+\.\s+)?)\[\s*([\s\S]*?\\(?:frac|big|left|right|sum|int|cdot|times|sqrt|alpha|beta|gamma|theta|pi|begin|end)[\s\S]*?)\s*\](\s*)$/;

const STANDALONE_EQUATION_RE =
  /^(\s*(?:[-*+]\s+|\d+\.\s+)?)(?!.*[`$])(?!.*\\\()([A-Za-z][A-Za-z0-9_]*(?:\([^)\n]+\))?\s*=\s*[^.!?]+(?:=\s*[^.!?]+)+)(\s*)$/;

function isEscaped(text, index) {
  let backslashCount = 0;
  for (let probe = index - 1; probe >= 0 && text[probe] === '\\'; probe -= 1) {
    backslashCount += 1;
  }
  return (backslashCount % 2) === 1;
}

function hasUnescapedDollar(value) {
  const text = String(value ?? '');
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === '$' && !isEscaped(text, index)) {
      return true;
    }
  }
  return false;
}

function findLiteralDelimiterIssue(value) {
  const text = String(value ?? '');
  const stack = [];
  const closers = {
    ')': '(',
    ']': '[',
  };
  for (let index = 0; index < text.length; index += 1) {
    const ch = text[index];
    if (!'()[]'.includes(ch) || isEscaped(text, index)) {
      continue;
    }
    if (ch === '(' || ch === '[') {
      stack.push(ch);
      continue;
    }
    if (stack.length === 0) {
      return `Unmatched closing delimiter '${ch}'`;
    }
    const opener = stack.pop();
    if (closers[ch] !== opener) {
      return `Mismatched delimiters '${opener}' and '${ch}'`;
    }
  }
  if (stack.length > 0) {
    return `Unclosed literal delimiter '${stack[stack.length - 1]}'`;
  }
  return null;
}

function hasDanglingOperator(value) {
  return DANGLING_OPERATOR_RE.test(String(value ?? '').trim());
}

function looksLikeCurrencyOrUnitText(value) {
  const text = String(value ?? '').trim();
  if (!text) {
    return false;
  }
  const hasDigits = /\d/.test(text);
  const hasLetters = /[A-Za-z]/.test(text);
  const hasUnitSlash = /\/[A-Za-z%]/.test(text);
  const hasMathSignals = MATH_SIGNAL_RE.test(text);
  return hasDigits && hasLetters && hasUnitSlash && !hasMathSignals;
}

function looksLikeSentenceFragment(value) {
  const text = String(value ?? '').trim();
  if (!text || MATH_SIGNAL_RE.test(text)) {
    return false;
  }
  const words = text.match(/[A-Za-z]{3,}/g) || [];
  return words.length >= 2;
}

function wrapInlineMath(expression) {
  return `$${String(expression ?? '').trim()}$`;
}

function wrapDisplayMath(expression) {
  return '\n\n$$\n' + String(expression ?? '').trim() + '\n$$\n\n';
}

function unwrapSingleDollarMath(value) {
  const text = String(value ?? '').trim();
  if (!text.startsWith('$') || !text.endsWith('$') || text.startsWith('$$') || text.endsWith('$$')) {
    return null;
  }
  const expression = text.slice(1, -1);
  if (hasUnescapedDollar(expression)) {
    return null;
  }
  return expression;
}

function unwrapRedundantMathWrapper(value) {
  const text = String(value ?? '').trim();
  const inlineParenMatch = text.match(/^\\\(([\s\S]*?)\\\)$/);
  if (inlineParenMatch) {
    return inlineParenMatch[1];
  }

  const displayBracketMatch = text.match(/^\\\[([\s\S]*?)\\\]$/);
  if (displayBracketMatch) {
    return displayBracketMatch[1];
  }

  const blockDollarMatch = text.match(/^\$\$([\s\S]*?)\$\$$/);
  if (blockDollarMatch) {
    return blockDollarMatch[1];
  }

  return unwrapSingleDollarMath(text);
}

function collapseRedundantMathWrappers(value) {
  let current = String(value ?? '').trim();
  let next = unwrapRedundantMathWrapper(current);
  while (typeof next === 'string') {
    current = String(next).trim();
    next = unwrapRedundantMathWrapper(current);
  }
  return current;
}

function canonicalizeLegacyNestedMath(value) {
  return String(value ?? '')
    .replace(LEGACY_NESTED_DISPLAY_PAREN_RE, (_, expr) => wrapDisplayMath(collapseRedundantMathWrappers(expr)))
    .replace(LEGACY_NESTED_DISPLAY_BRACKET_RE, (_, expr) => wrapDisplayMath(collapseRedundantMathWrappers(expr)))
    .replace(LEGACY_NESTED_INLINE_BRACKET_RE, (_, expr) => wrapDisplayMath(collapseRedundantMathWrappers(expr)))
    .replace(LEGACY_NESTED_INLINE_PAREN_RE, (_, expr) => wrapInlineMath(collapseRedundantMathWrappers(expr)));
}

function protectExplicitDisplayMath(value) {
  const placeholders = [];
  const protectedText = String(value ?? '').replace(
    EXPLICIT_DISPLAY_BLOCK_RE,
    (_, bracketExpr, dollarExpr) => {
      const expression = collapseRedundantMathWrappers(bracketExpr ?? dollarExpr ?? '');
      const placeholder = `@@RA_DISPLAY_MATH_${placeholders.length}@@`;
      placeholders.push(wrapDisplayMath(expression));
      return placeholder;
    }
  );
  return { protectedText, placeholders };
}

function restoreExplicitDisplayMath(value, placeholders) {
  let restored = String(value ?? '');
  placeholders.forEach((block, index) => {
    restored = restored.replace(`@@RA_DISPLAY_MATH_${index}@@`, () => block);
  });
  return restored;
}

export function normalizeMarkdownMath(value) {
  const canonicalized = canonicalizeLegacyNestedMath(value);
  const { protectedText, placeholders } = protectExplicitDisplayMath(canonicalized);

  const normalized = protectedText
    .split('\n')
    .map((line) => {
      const bracketMatch = line.match(STANDALONE_BRACKET_LATEX_RE);
      if (bracketMatch) {
        const [, prefix, expr, suffix] = bracketMatch;
        return `${prefix}` + wrapDisplayMath(expr).trim() + `${suffix}`;
      }

      const equationMatch = line.match(STANDALONE_EQUATION_RE);
      if (equationMatch) {
        const [, prefix, expr, suffix] = equationMatch;
        return `${prefix}\\(${String(expr).trim()}\\)${suffix}`;
      }

      return line;
    })
    .join('\n');

  return restoreExplicitDisplayMath(normalized, placeholders);
}

function createInlineMathNode(value) {
  const expression = String(value ?? '');
  return {
    type: 'inlineMath',
    value: expression,
    data: {
      hName: 'code',
      hProperties: {
        className: ['language-math', 'math-inline'],
      },
      hChildren: [{ type: 'text', value: expression }],
    },
  };
}

function transformTextNodeToExplicitInlineMath(node) {
  const text = String(node?.value ?? '');
  if (!text.includes('\\(')) {
    return [node];
  }

  const nextChildren = [];
  let lastIndex = 0;
  INLINE_EXPLICIT_MATH_RE.lastIndex = 0;
  let match = INLINE_EXPLICIT_MATH_RE.exec(text);
  while (match) {
    const start = match.index;
    const end = start + match[0].length;
    if (start > lastIndex) {
      nextChildren.push({ type: 'text', value: text.slice(lastIndex, start) });
    }
    nextChildren.push(createInlineMathNode(match[1]));
    lastIndex = end;
    match = INLINE_EXPLICIT_MATH_RE.exec(text);
  }

  if (lastIndex < text.length) {
    nextChildren.push({ type: 'text', value: text.slice(lastIndex) });
  }

  return nextChildren.length > 0 ? nextChildren : [node];
}

function visitChildArrays(node, visitor) {
  if (!node || typeof node !== 'object') {
    return;
  }
  if (Array.isArray(node.children)) {
    visitor(node);
    for (const child of node.children) {
      visitChildArrays(child, visitor);
    }
  }
}

export function remarkExplicitInlineMath() {
  return (tree) => {
    visitChildArrays(tree, (parent) => {
      const nextChildren = [];
      for (const child of parent.children) {
        if (child?.type === 'text') {
          nextChildren.push(...transformTextNodeToExplicitInlineMath(child));
          continue;
        }
        nextChildren.push(child);
      }
      parent.children = nextChildren;
    });
  };
}

function getRawSlice(node, source) {
  const start = node?.position?.start?.offset;
  const end = node?.position?.end?.offset;
  if (typeof start !== 'number' || typeof end !== 'number' || start < 0 || end < start) {
    return '';
  }
  return String(source ?? '').slice(start, end);
}

function isSingleDollarRawSlice(raw) {
  return raw.startsWith('$') && raw.endsWith('$') && !raw.startsWith('$$') && !raw.endsWith('$$');
}

export function shouldDowngradeSingleDollarMath({ expression, raw, source, endOffset }) {
  const expr = String(expression ?? '');
  const rawSlice = String(raw ?? '');
  if (!isSingleDollarRawSlice(rawSlice)) {
    return false;
  }

  if (!expr.trim()) {
    return true;
  }
  if (hasUnescapedDollar(expr)) {
    return true;
  }
  if (findLiteralDelimiterIssue(expr)) {
    return true;
  }
  if (hasDanglingOperator(expr)) {
    return true;
  }

  const nextChar = typeof endOffset === 'number' ? String(source ?? '')[endOffset] || '' : '';
  if (looksLikeCurrencyOrUnitText(expr) && /\d/.test(nextChar)) {
    return true;
  }
  if (looksLikeCurrencyOrUnitText(expr) || looksLikeSentenceFragment(expr)) {
    return true;
  }
  return false;
}

export function remarkSingleDollarCompat(options = {}) {
  const source = String(options.source ?? '');
  return (tree) => {
    visitChildArrays(tree, (parent) => {
      parent.children = parent.children.map((child) => {
        if (child?.type !== 'inlineMath') {
          return child;
        }
        const raw = getRawSlice(child, source);
        if (
          shouldDowngradeSingleDollarMath({
            expression: child.value,
            raw,
            source,
            endOffset: child?.position?.end?.offset,
          })
        ) {
          return { type: 'text', value: raw || `$${child.value}$` };
        }
        return child;
      });
    });
  };
}
