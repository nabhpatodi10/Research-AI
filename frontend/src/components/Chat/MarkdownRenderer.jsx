import 'github-markdown-css/github-markdown.css';
import 'katex/dist/katex.min.css';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeKatex from 'rehype-katex';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
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

const MarkdownRenderer = ({ content, variant = 'assistant' }) => {
  const normalizedContent = normalizeMathDelimiters(content);
  const renderedContent =
    variant === 'user' ? preserveUserLineBreaks(normalizedContent) : normalizedContent;
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
          [rehypeKatex, { output: 'html' }],
          rehypeHighlight,
          [rehypeSanitize, sanitizeSchema],
        ]}
        components={{
          code({ className, children, ...props }) {
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
