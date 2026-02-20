import { useCallback, useMemo, useRef, useState } from 'react';

const COMMAND_OPTIONS = [
  {
    command: '/research',
    label: '/research',
    description: 'Run deep research and generate a full research document.',
  },
];

const RESEARCH_COMMAND_PATTERN = /^\s*\/research(?:\s+([\s\S]*))?$/i;

const getSlashTokenInfo = (value, cursorPosition) => {
  const text = String(value ?? '');
  const cursor = Number.isFinite(cursorPosition) ? cursorPosition : text.length;
  const head = text.slice(0, cursor);
  const tokenMatch = head.match(/(?:^|\s)(\/[^\s]*)$/);
  if (!tokenMatch) return null;
  const token = tokenMatch[1];
  const start = head.length - token.length;
  return { token, start, end: cursor };
};

export function parseResearchCommand(value) {
  const raw = String(value ?? '');
  const matched = raw.match(RESEARCH_COMMAND_PATTERN);
  if (!matched) {
    return { isResearchCommand: false, topic: '', isEmptyResearchCommand: false };
  }
  const topic = String(matched[1] ?? '').trim();
  return {
    isResearchCommand: true,
    topic,
    isEmptyResearchCommand: topic.length === 0,
  };
}

export function useChatComposer({ initialValue = '' } = {}) {
  const [input, setInput] = useState(initialValue);
  const [composerError, setComposerError] = useState('');
  const [showCommandMenu, setShowCommandMenu] = useState(false);
  const [commandSuggestions, setCommandSuggestions] = useState([]);
  const [activeCommandIndex, setActiveCommandIndex] = useState(0);
  const commandTokenRangeRef = useRef({ start: 0, end: 0 });

  const closeCommandMenu = useCallback(() => {
    setShowCommandMenu(false);
    setCommandSuggestions([]);
    setActiveCommandIndex(0);
  }, []);

  const updateCommandSuggestions = useCallback(
    (value, cursorPosition) => {
      const tokenInfo = getSlashTokenInfo(value, cursorPosition);
      if (!tokenInfo || !tokenInfo.token.startsWith('/')) {
        closeCommandMenu();
        return;
      }

      const tokenLower = tokenInfo.token.toLowerCase();
      const suggestions = COMMAND_OPTIONS.filter((option) =>
        option.command.toLowerCase().startsWith(tokenLower)
      );
      if (suggestions.length === 0) {
        closeCommandMenu();
        return;
      }

      commandTokenRangeRef.current = { start: tokenInfo.start, end: tokenInfo.end };
      setCommandSuggestions(suggestions);
      setActiveCommandIndex(0);
      setShowCommandMenu(true);
    },
    [closeCommandMenu]
  );

  const applyCommandSuggestion = useCallback(
    (command, textareaNode = null) => {
      const sourceText = textareaNode?.value ?? input;
      const { start, end } = commandTokenRangeRef.current;
      const before = sourceText.slice(0, start);
      const after = sourceText.slice(end);
      const inserted = `${command} `;
      const nextValue = `${before}${inserted}${after}`;
      const nextCursor = before.length + inserted.length;

      setInput(nextValue);
      setComposerError('');
      closeCommandMenu();

      return nextCursor;
    },
    [closeCommandMenu, input]
  );

  const isEmptyResearchCommand = useMemo(
    () => parseResearchCommand(input).isEmptyResearchCommand,
    [input]
  );

  return {
    input,
    setInput,
    composerError,
    setComposerError,
    showCommandMenu,
    setShowCommandMenu,
    commandSuggestions,
    activeCommandIndex,
    setActiveCommandIndex,
    closeCommandMenu,
    updateCommandSuggestions,
    applyCommandSuggestion,
    isEmptyResearchCommand,
  };
}
