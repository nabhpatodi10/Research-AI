import 'github-markdown-css/github-markdown.css';
import 'katex/dist/katex.min.css';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeKatex from 'rehype-katex';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import ChartBlock from './ChartBlock';
import MermaidBlock from './MermaidBlock';
import './github-markdown-overrides.css'; // Optional custom overrides

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames || []), 'span', 'div'],
  attributes: {
    ...defaultSchema.attributes,
    div: [...(defaultSchema.attributes?.div || []), 'className', 'ariaHidden'],
    span: [
      ...(defaultSchema.attributes?.span || []),
      'className',
      'style',
      'title',
      'ariaHidden',
      'ariaLabel',
    ],
    code: [...(defaultSchema.attributes?.code || []), 'className'],
    pre: [...(defaultSchema.attributes?.pre || []), 'className'],
  },
};

const normalizeMathDelimiters = (value) => {
  const text = String(value ?? '');
  const normalizedBackslashDelimiters = text
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_, expr) => `$$${expr}$$`)
    .replace(/\\\((.+?)\\\)/gs, (_, expr) => `$${expr}$`);

  const normalizedBracketLatex = normalizedBackslashDelimiters.replace(
    /\[\s*(?=[^\]]*\\(?:frac|big|left|right|sum|int|cdot|times|sqrt|alpha|beta|gamma|theta|pi|begin|end))([\s\S]*?)\s*\]/g,
    (_, expr) => `$$${expr.trim()}$$`
  );

  // Heuristic for common model output: chained inline equations without explicit delimiters.
  // Example: U_i(x; v) = (...) = (...)
  return normalizedBracketLatex.replace(
    /([A-Za-z][A-Za-z0-9_]*\([^)\n]*\)\s*=\s*[^,\n=]+(?:=\s*[^,\n=]+)+)(?=\s+and\s+|\s*$|[.;:])/g,
    (_, expr) => `$${expr.trim()}$`
  );
};

const preserveUserLineBreaks = (value) =>
  String(value ?? '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\n/g, '  \n');

const classHasToken = (className, token) => {
  if (!className || !token) return false;
  return String(className)
    .split(/\s+/)
    .some((item) => item === token);
};

const extractLanguageFromClassName = (className) => {
  if (!className) return '';
  const match = String(className).match(/(?:^|\s)language-([^\s]+)/i);
  return match?.[1] ? String(match[1]).trim().toLowerCase() : '';
};

const extractChildrenText = (children) => {
  if (children === null || children === undefined) return '';
  if (typeof children === 'string' || typeof children === 'number') {
    return String(children);
  }
  if (Array.isArray(children)) {
    return children.map((child) => extractChildrenText(child)).join('');
  }
  if (typeof children === 'object' && children?.props?.children !== undefined) {
    return extractChildrenText(children.props.children);
  }
  return '';
};

const hashString = (value) => {
  const source = String(value ?? '');
  let hash = 0;
  for (let index = 0; index < source.length; index += 1) {
    hash = (hash << 5) - hash + source.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
};

const normalizeEscapedRichBlockContent = (value) => {
  const raw = String(value ?? '');
  const escapedNewlineMatches = raw.match(/\\r\\n|\\n|\\r/g) || [];
  const realNewlineMatches = raw.match(/\r\n|\n|\r/g) || [];
  const escapedNewlineCount = escapedNewlineMatches.length;
  const realNewlineCount = realNewlineMatches.length;

  if (escapedNewlineCount < 2 || escapedNewlineCount <= realNewlineCount) {
    return raw;
  }

  return raw
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\');
};

const normalizeEscapedAssistantContent = (value, variant) => {
  const raw = String(value ?? '');
  if (variant === 'user') {
    return raw;
  }

  const escapedNewlineMatches = raw.match(/\\r\\n|\\n|\\r/g) || [];
  const realNewlineMatches = raw.match(/\r\n|\n|\r/g) || [];
  const escapedNewlineCount = escapedNewlineMatches.length;
  const realNewlineCount = realNewlineMatches.length;
  if (escapedNewlineCount < 2 || escapedNewlineCount <= realNewlineCount) {
    return raw;
  }

  const hasMarkdownHints =
    raw.includes('\\n```') ||
    raw.includes('\\r\\n```') ||
    raw.includes('\\`\\`\\`') ||
    raw.includes('\\n#') ||
    raw.includes('\\n---');
  if (!hasMarkdownHints) {
    return raw;
  }

  return raw
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\"/g, '"')
    .replace(/\\`/g, '`')
    .replace(/\\\\/g, '\\');
};

const MarkdownRenderer = ({ content, variant = 'assistant' }) => {
  const transportNormalizedContent = normalizeEscapedAssistantContent(content, variant);
  const normalizedContent = normalizeMathDelimiters(transportNormalizedContent);
  const renderedContent =
    variant === 'user' ? preserveUserLineBreaks(normalizedContent) : normalizedContent;
  const enableRichCodeBlocks = variant === 'assistant';
  const variantClassName =
    variant === 'user'
      ? 'markdown-body--user'
      : variant === 'error'
        ? 'markdown-body--error'
        : 'markdown-body--assistant';

  return (
    <div className={`markdown-body ${variantClassName}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[
          [rehypeKatex, { output: 'html', throwOnError: false, strict: 'ignore' }],
          rehypeHighlight,
          [rehypeSanitize, sanitizeSchema],
        ]}
        components={{
          span({ className, children, title, ...props }) {
            if (classHasToken(className, 'katex-error')) {
              const source = extractChildrenText(children).trim();
              const reason = String(title || '').trim() || 'Invalid equation syntax.';
              return (
                <span className="ra-equation-error-shell" role="alert">
                  <span className="ra-equation-error-label">Equation could not be rendered</span>
                  <span className="ra-equation-error-message">{reason}</span>
                  {source ? <code className="ra-equation-error-source">{source}</code> : null}
                </span>
              );
            }
            return (
              <span className={className} {...props}>
                {children}
              </span>
            );
          },
          code({ className, children, inline, node, ...props }) {
            const language = extractLanguageFromClassName(className);
            if (!inline && enableRichCodeBlocks && (language === 'mermaid' || language === 'chartjson')) {
              const rawCode = extractChildrenText(children)
                .replace(/\r\n/g, '\n')
                .replace(/\r/g, '\n')
                .replace(/\n$/, '')
                .trim();
              const normalizedCode = normalizeEscapedRichBlockContent(rawCode).trim();
              const positionKey = `${node?.position?.start?.line || 0}:${node?.position?.start?.column || 0}`;
              const stableId = `${language}-${hashString(`${positionKey}:${normalizedCode}`)}`;

              if (language === 'mermaid') {
                return (
                  <MermaidBlock
                    definition={normalizedCode}
                    diagramId={`md-mermaid-${stableId}`}
                  />
                );
              }

              return (
                <ChartBlock
                  specSource={normalizedCode}
                  chartId={`md-chart-${stableId}`}
                />
              );
            }

            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          table({ children, ...props }) {
            return (
              <div className="markdown-table-shell">
                <div className="markdown-table-wrap">
                  <table {...props}>{children}</table>
                </div>
              </div>
            );
          },
        }}
      >
        {renderedContent}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;
