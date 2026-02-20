import { Suspense, lazy, useEffect, useMemo } from 'react';

import { parseAssistantRichBlocks } from './parseAssistantRichBlocks';

const ChartBlock = lazy(() => import('./ChartBlock'));
const MarkdownRenderer = lazy(() => import('./MarkdownRenderer'));
const MermaidBlock = lazy(() => import('./MermaidBlock'));

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
            <Suspense key={key} fallback={null}>
              <ChartBlock
                specSource={block.content}
                chartId={`assistant-chart-${index}`}
              />
            </Suspense>
          );
        }

        if (block.type === 'mermaid') {
          return (
            <Suspense key={key} fallback={null}>
              <MermaidBlock
                definition={block.content}
                diagramId={`assistant-mermaid-${index}`}
              />
            </Suspense>
          );
        }

        return (
          <Suspense
            key={key}
            fallback={<div className="px-4 py-3 text-sm text-slate-500 whitespace-pre-wrap">{block.content}</div>}
          >
            <MarkdownRenderer content={block.content} variant="assistant" />
          </Suspense>
        );
      })}
    </div>
  );
}

