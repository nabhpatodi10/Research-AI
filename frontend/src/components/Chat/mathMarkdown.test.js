import test from 'node:test';
import assert from 'node:assert/strict';
import katex from 'katex';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import {
  normalizeMarkdownMath,
  remarkExplicitInlineMath,
  remarkSingleDollarCompat,
  shouldDowngradeSingleDollarMath,
} from './mathMarkdown.js';

function runTree(source) {
  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkExplicitInlineMath)
    .use(remarkMath, { singleDollarTextMath: true })
    .use(remarkSingleDollarCompat, { source });
  const tree = processor.parse(source);
  return processor.runSync(tree);
}

function runNormalizedTree(source) {
  const normalized = normalizeMarkdownMath(source);
  return {
    normalized,
    tree: runTree(normalized),
  };
}

function collectNodeTypes(tree) {
  const types = [];
  const walk = (node) => {
    if (!node || typeof node !== 'object') {
      return;
    }
    if (node.type) {
      types.push(node.type);
    }
    if (Array.isArray(node.children)) {
      for (const child of node.children) {
        walk(child);
      }
    }
  };
  walk(tree);
  return types;
}

function collectNodesByType(tree, expectedType) {
  const nodes = [];
  const walk = (node) => {
    if (!node || typeof node !== 'object') {
      return;
    }
    if (node.type === expectedType) {
      nodes.push(node);
    }
    if (Array.isArray(node.children)) {
      for (const child of node.children) {
        walk(child);
      }
    }
  };
  walk(tree);
  return nodes;
}

test('preserves valid legacy single-dollar inline math', () => {
  const tree = runTree('Valid inline math $f(x)=x^2$ here.');
  const types = collectNodeTypes(tree);
  assert.equal(types.filter((type) => type === 'inlineMath').length, 1);
});

test('downgrades currency-like prose misparsed as single-dollar math', () => {
  const tree = runTree('Battery premium (50 kWh × $156/kWh) = $7,800.');
  const types = collectNodeTypes(tree);
  assert.equal(types.filter((type) => type === 'inlineMath').length, 0);
});

test('keeps double-dollar math untouched', () => {
  const tree = runTree('$$x^2 + y^2 = z^2$$');
  const types = collectNodeTypes(tree);
  assert.equal(types.filter((type) => type === 'inlineMath').length, 1);
});

test('normalizes explicit delimiters without manufacturing single-dollar math', () => {
  const normalized = normalizeMarkdownMath('Inline \\(a+b\\) and display \\[x^2\\]');
  assert.match(normalized, /\\\(a\+b\\\)/);
  assert.match(normalized, /\$\$\s*x\^2\s*\$\$/);
});

test('keeps explicit display equations out of the standalone equation heuristic', () => {
  const normalized = normalizeMarkdownMath(
    String.raw`\[
m = \frac{M\cdot Q}{z\cdot F} = \frac{M\cdot I t}{z\cdot F},
\]`
  );
  assert.match(normalized, /\$\$\s*m = \\frac{M\\cdot Q}{z\\cdot F} = \\frac{M\\cdot I t}{z\\cdot F},\s*\$\$/s);
  assert.doesNotMatch(normalized, /\$\$\s*\\\(/s);
  assert.doesNotMatch(normalized, /\\\)\s*\$\$/s);
});

test('full markdown pipeline keeps the stored backend display equation renderable', () => {
  const { normalized, tree } = runNormalizedTree(
    String.raw`\[
m = \frac{M\cdot Q}{z\cdot F} = \frac{M\cdot I t}{z\cdot F},
\]`
  );
  assert.doesNotMatch(normalized, /\$\$\s*\\\(/s);

  const mathNodes = collectNodesByType(tree, 'math');
  assert.equal(mathNodes.length, 1);
  assert.equal(
    mathNodes[0].value.trim(),
    String.raw`m = \frac{M\cdot Q}{z\cdot F} = \frac{M\cdot I t}{z\cdot F},`
  );
  assert.doesNotThrow(() =>
    katex.renderToString(mathNodes[0].value, {
      displayMode: true,
      throwOnError: true,
      strict: 'error',
    })
  );
});

test('standalone equation heuristic wraps only standalone equation-like lines', () => {
  const normalized = normalizeMarkdownMath(
    ['U_i(x; v) = a = b', 'The value U_i(x; v) = a = b appears inside prose.'].join('\n')
  );
  assert.match(normalized, /^\\\(U_i\(x; v\) = a = b\\\)$/m);
  assert.doesNotMatch(normalized, /The value .*\\\(/);
});

test('legacy malformed nested inline math is canonicalized and still renders', () => {
  const { normalized, tree } = runNormalizedTree(String.raw`Legacy inline $\(a+b\)$ math.`);
  assert.equal(normalized, 'Legacy inline $a+b$ math.');

  const mathNodes = collectNodesByType(tree, 'inlineMath');
  assert.equal(mathNodes.length, 1);
  assert.equal(mathNodes[0].value, 'a+b');
  assert.doesNotThrow(() =>
    katex.renderToString(mathNodes[0].value, {
      displayMode: false,
      throwOnError: true,
      strict: 'error',
    })
  );
});

test('legacy malformed nested display math is canonicalized to a display block', () => {
  const { normalized, tree } = runNormalizedTree(String.raw`$$\(a+b\)$$`);
  assert.match(normalized, /\$\$\s*a\+b\s*\$\$/s);
  assert.doesNotMatch(normalized, /\\\(/);

  const mathNodes = collectNodesByType(tree, 'math');
  assert.equal(mathNodes.length, 1);
  assert.equal(mathNodes[0].value.trim(), 'a+b');
});

test('display blocks with equation-like lines are not re-wrapped inline', () => {
  const normalized = normalizeMarkdownMath(
    String.raw`\[
U_i(x; v) = a = b
\]`
  );
  assert.match(normalized, /\$\$\s*U_i\(x; v\) = a = b\s*\$\$/s);
  assert.doesNotMatch(normalized, /\\\(U_i\(x; v\) = a = b\\\)/);
});

test('classifier flags the reported currency span as suspicious', () => {
  const raw = '$156/kWh) = $';
  assert.equal(
    shouldDowngradeSingleDollarMath({
      expression: '156/kWh) = ',
      raw,
      source: `${raw}7,800.`,
      endOffset: raw.length,
    }),
    true
  );
});
