import test from 'node:test';
import assert from 'node:assert/strict';
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

test('standalone equation heuristic wraps only standalone equation-like lines', () => {
  const normalized = normalizeMarkdownMath(
    ['U_i(x; v) = a = b', 'The value U_i(x; v) = a = b appears inside prose.'].join('\n')
  );
  assert.match(normalized, /^\\\(U_i\(x; v\) = a = b\\\)$/m);
  assert.doesNotMatch(normalized, /The value .*\\\(/);
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
