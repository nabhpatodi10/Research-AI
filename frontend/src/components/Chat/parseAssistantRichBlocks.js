const RICH_BLOCK_PATTERN =
  /```+\s*(chartjson|mermaid)\b[^`\\\r\n]*(?:\r?\n|\\r\\n|\\n|\\r)([\s\S]*?)```+/gi;

function shouldDecodeEscapedTransport(raw) {
  const escapedNewlineMatches = raw.match(/\\r\\n|\\n|\\r/g) || [];
  const realNewlineMatches = raw.match(/\r\n|\n|\r/g) || [];
  const escapedNewlineCount = escapedNewlineMatches.length;
  const realNewlineCount = realNewlineMatches.length;
  return escapedNewlineCount >= 2 && escapedNewlineCount > realNewlineCount;
}

function decodeEscapedTransport(raw, { decodeBackticks = false } = {}) {
  let decoded = String(raw ?? '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\');

  if (decodeBackticks) {
    decoded = decoded.replace(/\\`/g, '`');
  }

  return decoded;
}

function containsEscapedFenceHints(raw) {
  const source = String(raw ?? '');
  return (
    source.includes('\\`\\`\\`mermaid') ||
    source.includes('\\`\\`\\`chartjson') ||
    source.includes('\\n```mermaid') ||
    source.includes('\\n```chartjson') ||
    source.includes('\\r\\n```mermaid') ||
    source.includes('\\r\\n```chartjson')
  );
}

function normalizeEscapedTransportContent(content) {
  const raw = String(content ?? '');
  if (!shouldDecodeEscapedTransport(raw)) {
    return raw;
  }

  const hasRichBlockHints =
    raw.includes('\\n```') ||
    raw.includes('\\r\\n```') ||
    raw.includes('\\`\\`\\`') ||
    raw.includes('```');
  if (!hasRichBlockHints) {
    return raw;
  }

  return decodeEscapedTransport(raw, { decodeBackticks: true });
}

function normalizeEscapedBlockContent(content) {
  const raw = String(content ?? '');
  if (!shouldDecodeEscapedTransport(raw)) {
    return raw;
  }

  return decodeEscapedTransport(raw);
}

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

function parseBlocksFromSource(source) {
  const normalizedSource = String(source ?? '');
  if (!normalizedSource) return [];

  const blocks = [];
  let cursor = 0;
  let match = null;
  RICH_BLOCK_PATTERN.lastIndex = 0;

  while ((match = RICH_BLOCK_PATTERN.exec(normalizedSource)) !== null) {
    const fullMatch = match[0];
    const blockType = match[1];
    const blockContent = match[2];
    const startIndex = match.index;
    const endIndex = startIndex + fullMatch.length;

    if (startIndex > cursor) {
      blocks.push(makeMarkdownBlock(normalizedSource.slice(cursor, startIndex)));
    }

    const normalizedBlockContent = normalizeEscapedBlockContent(blockContent);
    blocks.push(makeSpecialBlock(blockType, normalizedBlockContent.trim()));
    cursor = endIndex;
  }

  if (cursor < normalizedSource.length) {
    blocks.push(makeMarkdownBlock(normalizedSource.slice(cursor)));
  }

  if (blocks.length === 0) {
    return [makeMarkdownBlock(normalizedSource)];
  }

  const filtered = blocks.filter((block) => {
    if (block.type !== 'markdown') return true;
    return block.content.trim().length > 0;
  });

  return filtered.length > 0 ? filtered : [makeMarkdownBlock(normalizedSource)];
}

export function parseAssistantRichBlocks(content) {
  const rawSource = String(content ?? '');
  if (!rawSource) {
    return [];
  }

  const normalizedSource = normalizeEscapedTransportContent(rawSource);
  const primaryBlocks = parseBlocksFromSource(normalizedSource);
  const hasSpecialPrimary = primaryBlocks.some(
    (block) => block.type === 'mermaid' || block.type === 'chartjson'
  );
  if (hasSpecialPrimary) {
    return primaryBlocks;
  }

  if (!containsEscapedFenceHints(rawSource)) {
    return primaryBlocks;
  }

  // Fallback: decode transport escapes more aggressively and re-run parsing.
  const forcedDecoded = decodeEscapedTransport(rawSource, { decodeBackticks: true });
  const fallbackBlocks = parseBlocksFromSource(forcedDecoded);
  const hasSpecialFallback = fallbackBlocks.some(
    (block) => block.type === 'mermaid' || block.type === 'chartjson'
  );
  return hasSpecialFallback ? fallbackBlocks : primaryBlocks;
}

