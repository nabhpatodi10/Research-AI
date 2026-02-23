import { useEffect, useMemo } from 'react';

import { parseAssistantRichBlocks } from './parseAssistantRichBlocks';
import ChartBlock from './ChartBlock';
import MarkdownRenderer from './MarkdownRenderer';
import MermaidBlock from './MermaidBlock';

function logBlockBreakdown(blocks) {
  if (!import.meta.env.DEV) return;
  const summary = blocks.reduce(
    (acc, block) => {
      acc[block.type] = (acc[block.type] || 0) + 1;
      return acc;
    },
    { markdown: 0, chartjson: 0, mermaid: 0 }
  );
  console.debug('[chat-rich] parsed assistant blocks', summary);
}

function hasRichFenceHints(content) {
  const source = String(content ?? '');
  return (
    source.includes('```mermaid') ||
    source.includes('```chartjson') ||
    source.includes('\\`\\`\\`mermaid') ||
    source.includes('\\`\\`\\`chartjson')
  );
}

export default function RichAssistantMessage({ content, messageId }) {
  const parsedBlocks = useMemo(() => parseAssistantRichBlocks(content), [content]);
  const hasSpecialBlocks = useMemo(
    () => parsedBlocks.some((block) => block.type === 'mermaid' || block.type === 'chartjson'),
    [parsedBlocks]
  );
  const shouldFallbackToMarkdownOnly = useMemo(
    () => hasRichFenceHints(content) && !hasSpecialBlocks,
    [content, hasSpecialBlocks]
  );

  useEffect(() => {
    logBlockBreakdown(parsedBlocks);
  }, [parsedBlocks]);

  if (shouldFallbackToMarkdownOnly) {
    return <MarkdownRenderer content={content} variant="assistant" />;
  }

  return (
    <div className="ra-rich-assistant">
      {parsedBlocks.map((block, index) => {
        const key = `${block.type}-${index}`;
        const blockIdBase = `${String(messageId || 'assistant')}-${index}`;

        if (block.type === 'chartjson') {
          return (
            <div key={key}>
              <ChartBlock
                specSource={block.content}
                chartId={`assistant-chart-${blockIdBase}`}
              />
            </div>
          );
        }

        if (block.type === 'mermaid') {
          return (
            <div key={key}>
              <MermaidBlock
                definition={block.content}
                diagramId={`assistant-mermaid-${blockIdBase}`}
              />
            </div>
          );
        }

        return (
          <div key={key}>
            <MarkdownRenderer content={block.content} variant="assistant" />
          </div>
        );
      })}
    </div>
  );
}

