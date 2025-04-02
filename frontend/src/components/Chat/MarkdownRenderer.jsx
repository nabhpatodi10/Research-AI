import 'github-markdown-css/github-markdown.css';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import './github-markdown-overrides.css'; // Optional custom overrides

const MarkdownRenderer = ({ content }) => {
  return (
    <div className="markdown-body p-4">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          rehypeHighlight,
          rehypeSanitize({
            tagNames: ['code', 'pre', 'span'],
            attributes: {
              code: ['className'],
              pre: ['className'],
              span: ['className']
            }
          })
        ]}
        components={{
          code({ className, children, ...props }) {
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          }
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;