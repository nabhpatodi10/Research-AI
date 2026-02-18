import { useEffect, useMemo } from 'react';

import ChartBlock from './ChartBlock';
import MarkdownRenderer from './MarkdownRenderer';
import MermaidBlock from './MermaidBlock';
import { parseAssistantRichBlocks } from './parseAssistantRichBlocks';

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

export default function RichAssistantMessage({ content }) {
  const parsedBlocks = useMemo(() => parseAssistantRichBlocks(content), [content]);

  useEffect(() => {
    logBlockBreakdown(parsedBlocks);
  }, [parsedBlocks]);

  return (
    <div className="ra-rich-assistant">
      {parsedBlocks.map((block, index) => {
        const key = `${block.type}-${index}`;

        if (block.type === 'chartjson') {
          return (
            <ChartBlock
              key={key}
              specSource={block.content}
              chartId={`assistant-chart-${index}`}
            />
          );
        }

        if (block.type === 'mermaid') {
          return (
            <MermaidBlock
              key={key}
              definition={block.content}
              diagramId={`assistant-mermaid-${index}`}
            />
          );
        }

        return <MarkdownRenderer key={key} content={block.content} variant="assistant" />;
      })}
    </div>
  );
}

