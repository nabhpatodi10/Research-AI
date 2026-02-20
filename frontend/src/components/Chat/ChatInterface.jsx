import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { useAuth } from '../../context/AuthContext';
import { apiRequest } from '../../lib/api';
import ChatHistory from './ChatHistory';
import MarkdownRenderer from './MarkdownRenderer';

const createClientMessageId = () => {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return uuid;
  return `message-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const deriveSessionTitle = (text) => {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (!normalized) return 'Untitled Session';
  const maxLength = 72;
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 3)}...` : normalized;
};

const QUICK_PROMPTS = [
  'Create a 5-point market overview for AI copilots in healthcare.',
  'Compare top open-source RAG frameworks with practical tradeoffs.',
  'Build a launch-ready research brief for an AI tutor product.',
];

const COMMAND_OPTIONS = [
  {
    command: '/research',
    label: '/research',
    description: 'Run deep research and generate a full research document.',
  },
];

const RESEARCH_COMMAND_PATTERN = /^\s*\/research(?:\s+([\s\S]*))?$/i;

const parseResearchCommand = (value) => {
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
};

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

const CHAT_SETTINGS_STORAGE_KEY = 'ra-chat-settings-v1';
const DEFAULT_CHAT_SETTINGS = {
  model: 'pro',
  research_breadth: 'medium',
  research_depth: 'high',
  document_length: 'high',
};

const VALID_CHAT_SETTING_VALUES = {
  model: new Set(['mini', 'pro']),
  research_breadth: new Set(['low', 'medium', 'high']),
  research_depth: new Set(['low', 'high']),
  document_length: new Set(['low', 'medium', 'high']),
};

const sanitizeChatSettings = (candidate) => {
  if (!candidate || typeof candidate !== 'object') {
    return { ...DEFAULT_CHAT_SETTINGS };
  }

  return {
    model: VALID_CHAT_SETTING_VALUES.model.has(candidate.model)
      ? candidate.model
      : DEFAULT_CHAT_SETTINGS.model,
    research_breadth: VALID_CHAT_SETTING_VALUES.research_breadth.has(candidate.research_breadth)
      ? candidate.research_breadth
      : DEFAULT_CHAT_SETTINGS.research_breadth,
    research_depth: VALID_CHAT_SETTING_VALUES.research_depth.has(candidate.research_depth)
      ? candidate.research_depth
      : DEFAULT_CHAT_SETTINGS.research_depth,
    document_length: VALID_CHAT_SETTING_VALUES.document_length.has(candidate.document_length)
      ? candidate.document_length
      : DEFAULT_CHAT_SETTINGS.document_length,
  };
};

const isDesktopViewport = () => (typeof window !== 'undefined' ? window.innerWidth >= 768 : true);

const SidebarContent = ({
  sessions,
  sessionsLoading,
  sessionsError,
  activeSessionId,
  searchTerm,
  setSearchTerm,
  handleNewChat,
  handleDeleteChat,
  handleRenameChat,
  handleShareChat,
  loadChat,
}) => (
  <>
    <div className="border-b border-blue-100 px-4 pb-4 pt-3">
      <div className="rounded-2xl border border-blue-100/80 bg-gradient-to-br from-blue-50 via-white to-slate-50 p-4 shadow-sm">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-700">Workspace</p>
        <h1 className="brand-display mt-1 text-xl font-bold text-blue-900">ResearchAI Chat</h1>
        <p className="mt-2 text-xs text-slate-500">{sessions.length} sessions available</p>

        <button
          onClick={handleNewChat}
          className="mt-4 w-full rounded-xl bg-blue-900 px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800"
        >
          + New chat
        </button>
      </div>

      <div className="mt-3 relative">
        <svg
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m21 21-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />
        </svg>
        <input
          type="text"
          placeholder="Search sessions"
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
          className="w-full rounded-xl border border-blue-100 bg-white px-9 py-2.5 text-sm text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
        />
      </div>
    </div>

    <div className="flex-1 overflow-y-auto no-scrollbar px-3 pb-6 pt-3">
      <ChatHistory
        sessions={sessions}
        loading={sessionsLoading}
        error={sessionsError}
        activeSessionId={activeSessionId}
        onChatSelect={loadChat}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
        onShareChat={handleShareChat}
        searchTerm={searchTerm}
      />
    </div>
  </>
);

function MessageBubble({ msg }) {
  if (msg.status === 'pending') {
    return (
      <div className="max-w-full rounded-2xl border border-blue-200 bg-white px-4 py-3 shadow-sm md:max-w-[78%]">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-blue-900 animate-bounce [animation-delay:-0.2s]" />
          <span className="h-2 w-2 rounded-full bg-blue-900 animate-bounce [animation-delay:-0.1s]" />
          <span className="h-2 w-2 rounded-full bg-blue-900 animate-bounce" />
        </div>
      </div>
    );
  }

  const isUser = msg.sender === 'user';
  const isAssistant = msg.sender === 'ai';
  const isError = msg.sender === 'ai-error' || msg.sender === 'system-error';

  if (isUser) {
    return (
      <div className="max-w-full overflow-hidden rounded-2xl bg-blue-900 text-white shadow-sm md:max-w-[78%]">
        <div className="whitespace-pre-wrap break-words px-4 py-3 text-sm leading-6">
          {msg.text}
        </div>
      </div>
    );
  }

  const markdownVariant = isError ? 'error' : 'assistant';

  return (
    <div
      className={`max-w-full overflow-hidden rounded-2xl shadow-sm md:max-w-[78%] ${
        isAssistant
          ? 'border border-blue-100 bg-white text-slate-800'
          : 'border border-red-200 bg-red-50 text-red-700'
      }`}
    >
      <MarkdownRenderer content={msg.text} variant={markdownVariant} />
    </div>
  );
}

export default function ChatInterface() {
  const { currentUser } = useAuth();

  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState('');

  const [messages, setMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [sessionTitle, setSessionTitle] = useState('');

  const [input, setInput] = useState('');
  const [isGeneratingResponse, setIsGeneratingResponse] = useState(false);
  const [chatSettings, setChatSettings] = useState(() => {
    if (typeof window === 'undefined') {
      return { ...DEFAULT_CHAT_SETTINGS };
    }
    try {
      const raw = window.localStorage.getItem(CHAT_SETTINGS_STORAGE_KEY);
      if (!raw) return { ...DEFAULT_CHAT_SETTINGS };
      return sanitizeChatSettings(JSON.parse(raw));
    } catch {
      return { ...DEFAULT_CHAT_SETTINGS };
    }
  });

  const [isRenameModalOpen, setIsRenameModalOpen] = useState(false);
  const [renameSessionId, setRenameSessionId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [renameLoading, setRenameLoading] = useState(false);
  const [renameError, setRenameError] = useState('');

  const [isShareModalOpen, setIsShareModalOpen] = useState(false);
  const [shareSessionId, setShareSessionId] = useState(null);
  const [shareSessionTitle, setShareSessionTitle] = useState('');
  const [shareEmail, setShareEmail] = useState('');
  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState('');

  const [isSidebarOpen, setIsSidebarOpen] = useState(() => isDesktopViewport());
  const [isSettingsPanelOpen, setIsSettingsPanelOpen] = useState(() => isDesktopViewport());
  const [searchTerm, setSearchTerm] = useState('');
  const [composerError, setComposerError] = useState('');
  const [showCommandMenu, setShowCommandMenu] = useState(false);
  const [commandSuggestions, setCommandSuggestions] = useState([]);
  const [activeCommandIndex, setActiveCommandIndex] = useState(0);

  const sessionIdRef = useRef(sessionId);
  const isGeneratingRef = useRef(false);
  const composerRef = useRef(null);
  const commandTokenRangeRef = useRef({ start: 0, end: 0 });

  const applySessionTitleFromList = useCallback((allSessions, targetSessionId) => {
    if (!targetSessionId) return;
    const matched = allSessions.find((item) => item.id === targetSessionId);
    if (matched && matched.topic) {
      setSessionTitle(matched.topic);
    }
  }, []);

  const loadSessions = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) setSessionsLoading(true);
      try {
        const payload = await apiRequest('/chat/sessions', { method: 'GET' });
        const loadedSessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
        setSessions(loadedSessions);
        setSessionsError('');
        applySessionTitleFromList(loadedSessions, sessionIdRef.current);
      } catch (error) {
        console.error('Error loading sessions:', error);
        setSessionsError(error.message || 'Failed to load chat history');
      } finally {
        if (!silent) setSessionsLoading(false);
      }
    },
    [applySessionTitleFromList]
  );

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    if (!currentUser) return;
    loadSessions();
  }, [currentUser, loadSessions]);

  const resizeComposer = useCallback(() => {
    const textarea = composerRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const maxHeight = 180;
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, []);

  useEffect(() => {
    resizeComposer();
  }, [input, resizeComposer]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(CHAT_SETTINGS_STORAGE_KEY, JSON.stringify(chatSettings));
    } catch {
      // Ignore localStorage persistence errors.
    }
  }, [chatSettings]);

  const updateChatSetting = (key, value) => {
    setChatSettings((prev) =>
      sanitizeChatSettings({
        ...prev,
        [key]: value,
      })
    );
  };

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
    (command) => {
      const textarea = composerRef.current;
      const sourceText = textarea?.value ?? input;
      const { start, end } = commandTokenRangeRef.current;
      const before = sourceText.slice(0, start);
      const after = sourceText.slice(end);
      const inserted = `${command} `;
      const nextValue = `${before}${inserted}${after}`;
      const nextCursor = before.length + inserted.length;

      setInput(nextValue);
      setComposerError('');
      closeCommandMenu();

      requestAnimationFrame(() => {
        const target = composerRef.current;
        if (!target) return;
        target.focus();
        target.setSelectionRange(nextCursor, nextCursor);
      });
    },
    [closeCommandMenu, input]
  );

  const handleNewChat = () => {
    setMessages([]);
    setInput('');
    setSessionTitle('');
    setSessionId(null);
    sessionIdRef.current = null;
    setIsRenameModalOpen(false);
    setRenameSessionId(null);
    setRenameValue('');
    setRenameError('');
    setShareError('');
    setComposerError('');
    closeCommandMenu();
  };

  const handleRenameChat = (targetSessionId, currentTitle = 'Untitled Session') => {
    if (!targetSessionId) return;
    setRenameSessionId(targetSessionId);
    setRenameValue(currentTitle);
    setRenameError('');
    setIsRenameModalOpen(true);
  };

  const closeRenameModal = () => {
    setIsRenameModalOpen(false);
    setRenameSessionId(null);
    setRenameValue('');
    setRenameError('');
  };

  const handleRenameSubmit = async (event) => {
    event.preventDefault();
    if (!renameSessionId) return;

    const nextTitle = renameValue.trim();
    if (!nextTitle) {
      setRenameError('Chat name is required');
      return;
    }

    setRenameLoading(true);
    setRenameError('');
    try {
      const payload = await apiRequest(`/chat/sessions/${renameSessionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ topic: nextTitle }),
      });

      const updated = payload?.session;
      if (updated) {
        setSessions((prev) =>
          prev.map((session) => (session.id === updated.id ? { ...session, ...updated } : session))
        );
      }
      if (renameSessionId === sessionIdRef.current) {
        setSessionTitle(nextTitle);
      }
      closeRenameModal();
    } catch (error) {
      console.error('Error renaming chat:', error);
      setRenameError(error.message || 'Failed to rename chat');
    } finally {
      setRenameLoading(false);
    }
  };

  const handleDeleteChat = async (targetSessionId, targetTitle = 'Untitled Session') => {
    if (!targetSessionId) return;
    const shouldDelete = window.confirm(`Delete chat "${targetTitle}"?`);
    if (!shouldDelete) return;

    try {
      await apiRequest(`/chat/sessions/${targetSessionId}`, { method: 'DELETE' });
      setSessions((prev) => prev.filter((session) => session.id !== targetSessionId));

      if (targetSessionId === sessionIdRef.current) {
        handleNewChat();
      }
    } catch (error) {
      console.error('Error deleting chat:', error);
      setSessionsError(error.message || 'Failed to delete chat');
    }
  };

  const handleShareChat = (targetSessionId, targetTitle = 'Untitled Session') => {
    if (!targetSessionId) return;
    setShareSessionId(targetSessionId);
    setShareSessionTitle(targetTitle);
    setShareError('');
    setIsShareModalOpen(true);
  };

  const closeShareModal = () => {
    setIsShareModalOpen(false);
    setShareError('');
    setShareEmail('');
    setShareSessionId(null);
    setShareSessionTitle('');
  };

  const loadChat = async (selectedSessionId) => {
    if (!selectedSessionId) return;

    try {
      setChatLoading(true);
      setMessages([]);
      const payload = await apiRequest(`/chat/sessions/${selectedSessionId}/messages`, {
        method: 'GET',
      });
      const loadedMessages = Array.isArray(payload?.messages) ? payload.messages : [];
      setMessages(loadedMessages);
      setSessionId(selectedSessionId);
      sessionIdRef.current = selectedSessionId;
      applySessionTitleFromList(sessions, selectedSessionId);

      if (window.innerWidth < 768) {
        setIsSidebarOpen(false);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
      setMessages([{ id: 'system-error', text: 'Failed to load chat history.', sender: 'ai-error' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleSend = async (event) => {
    event.preventDefault();
    if (isGeneratingRef.current) return;

    const rawInput = input;
    const trimmedInput = rawInput.trim();
    const commandState = parseResearchCommand(rawInput);
    if (!trimmedInput) return;
    if (commandState.isEmptyResearchCommand) {
      setComposerError('Add a topic after /research before sending.');
      return;
    }

    const shouldForceResearch = commandState.isResearchCommand;
    const messageText = shouldForceResearch ? commandState.topic : trimmedInput;
    if (!messageText) return;

    isGeneratingRef.current = true;
    setIsGeneratingResponse(true);
    setComposerError('');
    closeCommandMenu();

    const pendingMessageId = `pending-${createClientMessageId()}`;
    setMessages((prev) => [
      ...prev,
      { id: `user-${createClientMessageId()}`, text: messageText, sender: 'user' },
      { id: pendingMessageId, text: '', sender: 'ai', status: 'pending' },
    ]);
    setInput('');

    if (!sessionTitle) {
      setSessionTitle(deriveSessionTitle(messageText));
    }

    try {
      const payload = await apiRequest('/chat', {
        method: 'POST',
        body: JSON.stringify({
          user_input: messageText,
          force_research: shouldForceResearch,
          session_id: sessionIdRef.current,
          model: chatSettings.model,
          research_breadth: chatSettings.research_breadth,
          research_depth: chatSettings.research_depth,
          document_length: chatSettings.document_length,
        }),
      });

      const returnedSessionId = String(payload?.session_id || '').trim();
      const responseText = String(payload?.response || '').trim();
      if (!responseText) {
        throw new Error('Empty response from backend');
      }

      if (returnedSessionId) {
        setSessionId(returnedSessionId);
        sessionIdRef.current = returnedSessionId;
      }

      setMessages((prev) =>
        prev.map((message) =>
          message.id === pendingMessageId
            ? { ...message, text: responseText, sender: 'ai', status: 'done' }
            : message
        )
      );
      await loadSessions({ silent: true });
    } catch (error) {
      console.error('Error sending message:', error);
      setMessages((prev) =>
        prev.map((message) =>
          message.id === pendingMessageId
            ? {
                ...message,
                text: "Sorry, I couldn't process your request.",
                sender: 'ai-error',
                status: 'error',
              }
            : message
        )
      );
    } finally {
      isGeneratingRef.current = false;
      setIsGeneratingResponse(false);
    }
  };

  const handleComposerKeyDown = (event) => {
    if (showCommandMenu) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeCommandMenu();
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setActiveCommandIndex((index) =>
          commandSuggestions.length === 0 ? 0 : (index + 1) % commandSuggestions.length
        );
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setActiveCommandIndex((index) =>
          commandSuggestions.length === 0
            ? 0
            : (index - 1 + commandSuggestions.length) % commandSuggestions.length
        );
        return;
      }
      if ((event.key === 'Enter' || event.key === 'Tab') && commandSuggestions.length > 0) {
        event.preventDefault();
        const selected = commandSuggestions[activeCommandIndex] || commandSuggestions[0];
        if (selected?.command) {
          applyCommandSuggestion(selected.command);
        }
        return;
      }
    }

    if (event.key !== 'Enter') return;
    if (event.shiftKey) return;

    event.preventDefault();
    if (chatLoading || isGeneratingResponse || !input.trim()) return;
    if (parseResearchCommand(input).isEmptyResearchCommand) {
      setComposerError('Add a topic after /research before sending.');
      return;
    }
    event.currentTarget.form?.requestSubmit();
  };

  const handleShareClick = () => {
    if (!sessionIdRef.current) return;
    handleShareChat(sessionIdRef.current, sessionTitle || 'Untitled Session');
  };

  const handleShareSubmit = async (event) => {
    event.preventDefault();
    setShareLoading(true);
    setShareError('');

    try {
      const targetSessionId = shareSessionId || sessionIdRef.current;
      if (!targetSessionId) {
        throw new Error('No chat selected to share');
      }
      await apiRequest(`/chat/sessions/${targetSessionId}/share`, {
        method: 'POST',
        body: JSON.stringify({ email: shareEmail.trim() }),
      });
      closeShareModal();
    } catch (error) {
      console.error('Sharing error:', error);
      setShareError(error.message || 'Failed to share chat');
    } finally {
      setShareLoading(false);
    }
  };

  const isEmptyResearchCommand = parseResearchCommand(input).isEmptyResearchCommand;

  return (
    <div className="relative flex h-screen overflow-hidden bg-gradient-to-b from-slate-50 via-blue-50/40 to-slate-100">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-24 right-0 h-72 w-72 rounded-full bg-blue-200/20 blur-3xl" />
        <div className="absolute -left-16 bottom-10 h-64 w-64 rounded-full bg-blue-900/10 blur-3xl" />
      </div>

      <Transition appear show={isRenameModalOpen} as={Fragment}>
        <Dialog as="div" className="relative z-30" onClose={closeRenameModal}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-200"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-150"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md overflow-hidden rounded-2xl border border-blue-100 bg-white p-6 shadow-xl">
                  <Dialog.Title className="text-lg font-semibold text-blue-900">Rename Chat Session</Dialog.Title>

                  <form onSubmit={handleRenameSubmit} className="mt-4 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700">Chat Name</label>
                      <input
                        type="text"
                        required
                        value={renameValue}
                        onChange={(event) => setRenameValue(event.target.value)}
                        className="mt-1 block w-full rounded-lg border border-blue-100 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>

                    {renameError && <p className="text-sm text-red-500">{renameError}</p>}

                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={closeRenameModal}
                        className="rounded-lg border border-blue-100 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-blue-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={renameLoading || !renameValue.trim()}
                        className="rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                      >
                        {renameLoading ? 'Renaming...' : 'Rename'}
                      </button>
                    </div>
                  </form>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>

      <Transition appear show={isShareModalOpen} as={Fragment}>
        <Dialog as="div" className="relative z-30" onClose={closeShareModal}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-200"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-150"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md overflow-hidden rounded-2xl border border-blue-100 bg-white p-6 shadow-xl">
                  <Dialog.Title className="text-lg font-semibold text-blue-900">Share Chat Session</Dialog.Title>
                  {shareSessionTitle && (
                    <p className="mt-1 text-sm text-slate-500">Sharing: {shareSessionTitle}</p>
                  )}

                  <form onSubmit={handleShareSubmit} className="mt-4 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700">Recipient Email</label>
                      <input
                        type="email"
                        required
                        value={shareEmail}
                        onChange={(event) => setShareEmail(event.target.value)}
                        className="mt-1 block w-full rounded-lg border border-blue-100 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>

                    {shareError && <p className="text-sm text-red-500">{shareError}</p>}

                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={closeShareModal}
                        className="rounded-lg border border-blue-100 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-blue-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={shareLoading || !shareEmail.trim()}
                        className="rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                      >
                        {shareLoading ? 'Sharing...' : 'Share'}
                      </button>
                    </div>
                  </form>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>

      <div
        id="mobile-chat-sidebar"
        className={`fixed inset-x-0 bottom-0 top-16 z-40 flex md:hidden ${isSidebarOpen ? '' : 'pointer-events-none'}`}
      >
        <div
          className={`fixed inset-x-0 bottom-0 top-16 bg-slate-900/35 transition-opacity ${isSidebarOpen ? 'opacity-100' : 'opacity-0'}`}
          onClick={() => setIsSidebarOpen(false)}
        />
        <div
          className={`relative flex w-80 max-w-[86%] flex-col border-r border-blue-100 bg-white/95 backdrop-blur-md transition-transform ${
            isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <SidebarContent
            sessions={sessions}
            sessionsLoading={sessionsLoading}
            sessionsError={sessionsError}
            activeSessionId={sessionId}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            handleNewChat={handleNewChat}
            handleDeleteChat={handleDeleteChat}
            handleRenameChat={handleRenameChat}
            handleShareChat={handleShareChat}
            loadChat={loadChat}
          />
        </div>
      </div>

      <aside
        className={`hidden border-r border-blue-100 bg-white/90 pt-16 backdrop-blur-md transition-all duration-300 md:flex md:flex-col ${
          isSidebarOpen ? 'w-[20rem]' : 'w-0 overflow-hidden border-r-0'
        }`}
      >
        {isSidebarOpen && (
          <SidebarContent
            sessions={sessions}
            sessionsLoading={sessionsLoading}
            sessionsError={sessionsError}
            activeSessionId={sessionId}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            handleNewChat={handleNewChat}
            handleDeleteChat={handleDeleteChat}
            handleRenameChat={handleRenameChat}
            handleShareChat={handleShareChat}
            loadChat={loadChat}
          />
        )}
      </aside>

      <main className="relative flex min-w-0 flex-1 flex-col pt-16">
        <header className="border-b border-blue-100/90 bg-white/75 px-4 py-3 backdrop-blur-md md:px-6">
          <div className="flex w-full items-center justify-between gap-3 md:pl-1">
            <div className="flex min-w-0 items-center gap-2">
              <button
                className="rounded-lg p-1.5 text-slate-600 transition hover:bg-blue-50 hover:text-blue-900 md:hidden"
                onClick={() => setIsSidebarOpen((value) => !value)}
                aria-label={isSidebarOpen ? 'Close sidebar' : 'Open sidebar'}
                aria-expanded={isSidebarOpen}
                aria-controls="mobile-chat-sidebar"
              >
                <span className="relative block h-5 w-5">
                  <span
                    className={`absolute left-0 h-0.5 w-5 rounded-full bg-current transition-all duration-200 ease-out ${
                      isSidebarOpen ? 'top-2.5 rotate-45' : 'top-1'
                    }`}
                  />
                  <span
                    className={`absolute left-0 top-2.5 h-0.5 w-5 rounded-full bg-current transition-all duration-200 ease-out ${
                      isSidebarOpen ? 'opacity-0' : 'opacity-100'
                    }`}
                  />
                  <span
                    className={`absolute left-0 h-0.5 w-5 rounded-full bg-current transition-all duration-200 ease-out ${
                      isSidebarOpen ? 'top-2.5 -rotate-45' : 'top-4'
                    }`}
                  />
                </span>
              </button>

              <button
                className="hidden rounded-lg p-1.5 text-slate-600 transition hover:bg-blue-50 hover:text-blue-900 md:block"
                onClick={() => setIsSidebarOpen((value) => !value)}
                aria-label="Toggle sidebar"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {isSidebarOpen ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 6l-6 6 6 6" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 6l6 6-6 6" />
                  )}
                </svg>
              </button>

              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-blue-700">
                  {sessionId ? 'Active Session' : 'New Session'}
                </p>
                <h2 className="truncate text-lg font-semibold text-slate-900 md:text-xl">
                  {sessionId ? sessionTitle || 'Untitled Session' : 'Start a new conversation'}
                </h2>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {isGeneratingResponse && (
                <span className="hidden items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 md:inline-flex">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-700 animate-pulse" />
                  Generating
                </span>
              )}

              {sessionId && (
                <button
                  onClick={handleShareClick}
                  className="rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm font-semibold text-blue-900 transition hover:bg-blue-50"
                >
                  Share
                </button>
              )}
            </div>
          </div>
        </header>

        <section className="flex-1 overflow-y-auto px-4 py-6 md:px-8 md:py-7">
          <div className="mx-auto w-full max-w-5xl">
            {chatLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((item) => (
                  <div key={item} className="animate-pulse rounded-2xl border border-blue-100 bg-white/90 p-4 shadow-sm">
                    <div className="h-3 w-24 rounded bg-blue-100" />
                    <div className="mt-3 h-2.5 w-full rounded bg-blue-50" />
                    <div className="mt-2 h-2.5 w-5/6 rounded bg-blue-50" />
                  </div>
                ))}
              </div>
            ) : messages.length === 0 ? (
              <div className="rounded-3xl border border-blue-100 bg-white/90 p-6 shadow-sm md:p-8">
                <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-900 text-white">
                  <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h8M8 14h5m7 5-4-4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8a4 4 0 0 1-1 2.646Z" />
                  </svg>
                </div>

                <h3 className="mt-4 text-2xl font-semibold text-slate-900">What are we researching today?</h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                  Ask for market scans, comparative analyses, strategy notes, or deep-dive summaries. I will structure the output as a clean research response.
                </p>

                <div className="mt-6 grid gap-2">
                  {QUICK_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setInput(prompt)}
                      className="rounded-xl border border-blue-100 bg-blue-50/50 px-4 py-3 text-left text-sm text-slate-700 transition hover:border-blue-200 hover:bg-blue-50"
                      disabled={isGeneratingResponse}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex w-full flex-col gap-4">
                {messages.map((msg, index) => {
                  const isUser = msg.sender === 'user';
                  const avatarClass = isUser ? 'bg-slate-900 text-white' : 'bg-blue-900 text-white';
                  const avatarText = isUser ? 'You' : 'AI';

                  return (
                    <div key={msg.id || index} className={`flex items-start gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
                      {!isUser && (
                        <div className={`mt-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-bold md:flex ${avatarClass}`}>
                          {avatarText}
                        </div>
                      )}
                      <MessageBubble msg={msg} />
                      {isUser && (
                        <div className={`mt-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-bold md:flex ${avatarClass}`}>
                          {avatarText}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        <footer className="border-t border-blue-100/90 bg-white/80 px-4 py-4 backdrop-blur-md md:px-8 md:py-5">
          <form onSubmit={handleSend} className="mx-auto w-full max-w-5xl">
            <div className="rounded-2xl border border-blue-100 bg-white p-2 shadow-sm">
              <div className="px-1 pb-2">
                <button
                  type="button"
                  onClick={() => setIsSettingsPanelOpen((value) => !value)}
                  aria-expanded={isSettingsPanelOpen}
                  aria-controls="chat-settings-panel"
                  className="flex w-full items-center justify-between rounded-xl border border-blue-100 bg-blue-50/40 px-3 py-2 text-left transition hover:bg-blue-50"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-blue-800">
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 21v-7m0 0a2 2 0 1 1 4 0m-4 0a2 2 0 1 0 4 0m6 7v-8m0 0a2 2 0 1 1 4 0m-4 0a2 2 0 1 0 4 0M8 7V3m0 4a2 2 0 1 1 4 0M8 7a2 2 0 1 0 4 0" />
                      </svg>
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-wide text-blue-900">Research Parameters</p>
                      <p className="truncate text-[11px] text-slate-500">
                        Model: {chatSettings.model} | Breadth: {chatSettings.research_breadth} | Depth: {chatSettings.research_depth} | Length: {chatSettings.document_length}
                      </p>
                    </div>
                  </div>
                  <svg
                    className={`h-4 w-4 shrink-0 text-slate-500 transition-transform ${isSettingsPanelOpen ? '' : 'rotate-180'}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m19 9-7 7-7-7" />
                  </svg>
                </button>
              </div>

              <Transition
                as={Fragment}
                show={isSettingsPanelOpen}
                enter="transition-[max-height,opacity,transform] duration-300 ease-out"
                enterFrom="max-h-0 -translate-y-1 opacity-0"
                enterTo="max-h-[24rem] translate-y-0 opacity-100"
                leave="transition-[max-height,opacity,transform] duration-200 ease-in"
                leaveFrom="max-h-[24rem] translate-y-0 opacity-100"
                leaveTo="max-h-0 -translate-y-1 opacity-0"
              >
                <div id="chat-settings-panel" className="overflow-hidden">
                  <div className="grid gap-2 px-1 pb-2 sm:grid-cols-2 lg:grid-cols-4">
                    <label className="flex flex-col gap-1 rounded-xl border border-blue-100 bg-blue-50/30 px-2.5 py-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-blue-800">Model</span>
                      <select
                        value={chatSettings.model}
                        onChange={(event) => updateChatSetting('model', event.target.value)}
                        disabled={chatLoading || isGeneratingResponse}
                        className="rounded-lg border border-blue-100 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      >
                        <option value="mini">Mini</option>
                        <option value="pro">Pro</option>
                      </select>
                    </label>
                    <label className="flex flex-col gap-1 rounded-xl border border-blue-100 bg-blue-50/30 px-2.5 py-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-blue-800">Breadth</span>
                      <select
                        value={chatSettings.research_breadth}
                        onChange={(event) => updateChatSetting('research_breadth', event.target.value)}
                        disabled={chatLoading || isGeneratingResponse}
                        className="rounded-lg border border-blue-100 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      >
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                    </label>
                    <label className="flex flex-col gap-1 rounded-xl border border-blue-100 bg-blue-50/30 px-2.5 py-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-blue-800">Depth</span>
                      <select
                        value={chatSettings.research_depth}
                        onChange={(event) => updateChatSetting('research_depth', event.target.value)}
                        disabled={chatLoading || isGeneratingResponse}
                        className="rounded-lg border border-blue-100 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      >
                        <option value="low">Low</option>
                        <option value="high">High</option>
                      </select>
                    </label>
                    <label className="flex flex-col gap-1 rounded-xl border border-blue-100 bg-blue-50/30 px-2.5 py-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-blue-800">Document Length</span>
                      <select
                        value={chatSettings.document_length}
                        onChange={(event) => updateChatSetting('document_length', event.target.value)}
                        disabled={chatLoading || isGeneratingResponse}
                        className="rounded-lg border border-blue-100 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      >
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                    </label>
                  </div>
                </div>
              </Transition>

              <div className="relative flex items-end gap-2">
                <textarea
                  ref={composerRef}
                  rows={1}
                  wrap="soft"
                  value={input}
                  onChange={(event) => {
                    const nextValue = event.target.value;
                    setInput(nextValue);
                    if (composerError) setComposerError('');
                    updateCommandSuggestions(nextValue, event.target.selectionStart ?? nextValue.length);
                  }}
                  onClick={(event) => {
                    updateCommandSuggestions(event.currentTarget.value, event.currentTarget.selectionStart);
                  }}
                  onKeyUp={(event) => {
                    updateCommandSuggestions(event.currentTarget.value, event.currentTarget.selectionStart);
                  }}
                  onBlur={() => {
                    setTimeout(() => closeCommandMenu(), 100);
                  }}
                  onKeyDown={handleComposerKeyDown}
                  placeholder={sessionId ? 'Ask a follow-up question...' : 'Describe what you want to research...'}
                  className="max-h-[180px] w-full resize-none rounded-xl border border-transparent bg-transparent px-3 py-2.5 text-sm leading-6 text-slate-800 outline-none focus:border-blue-100 whitespace-pre-wrap break-words"
                  disabled={chatLoading || isGeneratingResponse}
                />
                {showCommandMenu && commandSuggestions.length > 0 && (
                  <div
                    className="absolute bottom-full left-2 right-16 z-20 mb-2 overflow-hidden rounded-xl border border-blue-100 bg-white shadow-lg"
                    onMouseDown={(event) => event.preventDefault()}
                  >
                    {commandSuggestions.map((option, index) => (
                      <button
                        key={option.command}
                        type="button"
                        onClick={() => applyCommandSuggestion(option.command)}
                        className={`block w-full px-3 py-2 text-left transition ${
                          index === activeCommandIndex
                            ? 'bg-blue-50 text-blue-900'
                            : 'bg-white text-slate-700 hover:bg-blue-50'
                        }`}
                      >
                        <p className="text-sm font-semibold">{option.label}</p>
                        <p className="text-xs text-slate-500">{option.description}</p>
                      </button>
                    ))}
                  </div>
                )}
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={chatLoading || isGeneratingResponse || !input.trim() || isEmptyResearchCommand}
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10.5 22 3l-7.5 19-2.8-8.7L3 10.5Z" />
                  </svg>
                  Send
                </button>
              </div>

              <div className="flex items-center justify-between px-2 pb-1 pt-2 text-[11px] text-slate-500">
                <span>{isGeneratingResponse ? 'Wait for the current response to finish before sending another message.' : 'Enter to send. Shift+Enter for a new line.'}</span>
                <span>{sessionId ? 'Session active' : 'New session'}</span>
              </div>
              {composerError && (
                <p className="px-2 pb-1 text-xs text-red-600">{composerError}</p>
              )}
            </div>
          </form>
        </footer>
      </main>
    </div>
  );
}
