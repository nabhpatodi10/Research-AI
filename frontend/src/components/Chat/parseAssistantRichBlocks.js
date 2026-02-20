const RICH_BLOCK_PATTERN = /```(chartjson|mermaid)[ \t]*\r?\n([\s\S]*?)```/gi;

function makeMarkdownBlock(content) {
  return {
    type: 'markdown',
    content: String(content ?? ''),
  };
}

function makeSpecialBlock(type, content) {
  return {
    type: String(type || '').toLowerCase(),
    content: String(content ?? ''),
  };
}

export function parseAssistantRichBlocks(content) {
  const source = String(content ?? '');
  if (!source) {
    return [];
  }

  const blocks = [];
  let cursor = 0;
  let match = null;

  while ((match = RICH_BLOCK_PATTERN.exec(source)) !== null) {
    const fullMatch = match[0];
    const blockType = match[1];
    const blockContent = match[2];
    const startIndex = match.index;
    const endIndex = startIndex + fullMatch.length;

    if (startIndex > cursor) {
      blocks.push(makeMarkdownBlock(source.slice(cursor, startIndex)));
    }

    blocks.push(makeSpecialBlock(blockType, blockContent.trim()));
    cursor = endIndex;
  }

  if (cursor < source.length) {
    blocks.push(makeMarkdownBlock(source.slice(cursor)));
  }

  if (blocks.length === 0) {
    return [makeMarkdownBlock(source)];
  }

  const filtered = blocks.filter((block) => {
    if (block.type !== 'markdown') return true;
    return block.content.trim().length > 0;
  });

  return filtered.length > 0 ? filtered : [makeMarkdownBlock(source)];
}

