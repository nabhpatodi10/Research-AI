import { Fragment, useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Transition } from '@headlessui/react';
import { useAuth } from '../../context/useAuth';
import { apiRequest } from '../../lib/api';
import ChatLayout from './components/ChatLayout';
import ChatModals from './components/ChatModals';
import MessageList from './components/MessageList';
import SidebarContent from './components/SidebarContent';
import { parseResearchCommand, useChatComposer } from './hooks/useChatComposer';
import { useChatSessions } from './hooks/useChatSessions';
import { getResearchPendingMessageId, useResearchTasks } from './hooks/useResearchTasks';
import {
  NEW_SESSION_KEY,
  chatReducer,
  getSessionGenerating,
  initialChatState,
} from './reducer/chatReducer';

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

const CHAT_SETTINGS_STORAGE_KEY = 'ra-chat-settings-v1';
const AUTO_OPEN_RECENT_SESSION = true;
const DEFAULT_CHAT_SETTINGS = {
  model: 'pro',
  research_breadth: 'medium',
  research_depth: 'high',
  document_length: 'high',
};

const VALID_CHAT_SETTING_VALUES = {
  model: new Set(['mini', 'pro']),
  research_breadth: new Set(['low', 'medium', 'high']),
  research_depth: new Set(['low', 'medium', 'high']),
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

const findLastUserMessageIndex = (items) => {
  if (!Array.isArray(items) || items.length === 0) return -1;
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (items[index]?.sender === 'user') {
      return index;
    }
  }
  return -1;
};

const isResearchTaskOngoing = (task) => {
  const status = String(task?.status || '').trim().toLowerCase();
  return status === 'queued' || status === 'running';
};

export default function ChatInterface() {
  const { currentUser } = useAuth();
  const [chatState, dispatch] = useReducer(chatReducer, initialChatState);
  const { messages, chatLoading } = chatState;

  const [sessionId, setSessionId] = useState(null);
  const [sessionTitle, setSessionTitle] = useState('');

  const {
    sessions,
    sessionsLoading,
    sessionsError,
    setSessionsError,
    loadSessions,
    loadChatMessages,
    renameSession,
    deleteSession,
    shareSession,
  } = useChatSessions();

  const {
    input,
    setInput,
    composerError,
    setComposerError,
    showCommandMenu,
    commandSuggestions,
    activeCommandIndex,
    setActiveCommandIndex,
    closeCommandMenu,
    updateCommandSuggestions,
    applyCommandSuggestion,
    isEmptyResearchCommand,
  } = useChatComposer();

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
  const [shareCollaborative, setShareCollaborative] = useState(true);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState('');

  const [isSidebarOpen, setIsSidebarOpen] = useState(() => isDesktopViewport());
  const [isSettingsPanelOpen, setIsSettingsPanelOpen] = useState(() => isDesktopViewport());
  const [searchTerm, setSearchTerm] = useState('');

  const sessionIdRef = useRef(sessionId);
  const composerRef = useRef(null);
  const chatScrollContainerRef = useRef(null);
  const shouldScrollToLoadedUserMessageRef = useRef(false);
  const loadedUserMessageIndexRef = useRef(-1);
  const hasAttemptedAutoOpenRef = useRef(false);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const applySessionTitleFromList = useCallback((allSessions, targetSessionId) => {
    if (!targetSessionId) return;
    const matched = allSessions.find((item) => item.id === targetSessionId);
    if (matched && matched.topic) {
      setSessionTitle(matched.topic);
    }
  }, []);

  const refreshSessions = useCallback(
    async ({ silent = true } = {}) =>
      loadSessions({
        silent,
        activeSessionId: sessionIdRef.current,
        onApplySessionTitle: applySessionTitleFromList,
      }),
    [applySessionTitleFromList, loadSessions]
  );

  const ensurePendingResearchMessage = useCallback((pendingMessageId) => {
    dispatch({ type: 'ADD_PENDING_RESEARCH_MESSAGE', pendingMessageId });
  }, []);

  const handleTaskCompletedInActiveSession = useCallback(({ sessionId: taskSessionId, pendingMessageId, responseText, messageId }) => {
    dispatch({
      type: 'TASK_DONE',
      sessionId: taskSessionId,
      pendingMessageId,
      responseText,
      messageId,
    });
  }, []);

  const handleTaskFailedInActiveSession = useCallback(({ sessionId: taskSessionId, pendingMessageId, errorText, messageId }) => {
    dispatch({
      type: 'TASK_FAILED',
      sessionId: taskSessionId,
      pendingMessageId,
      errorText,
      messageId,
    });
  }, []);

  const handleTaskProgressInActiveSession = useCallback(
    ({ sessionId: taskSessionId, pendingMessageId, progressText }) => {
      dispatch({
        type: 'TASK_PROGRESS',
        sessionId: taskSessionId,
        pendingMessageId,
        progressText,
      });
    },
    []
  );

  const {
    taskBySession,
    upsertSessionTask,
    acknowledgeTerminalTask,
    applyActiveTaskSnapshot,
    refreshActiveTaskForSession,
    hasAnyOngoingTask,
    hasOngoingTaskForSession,
  } = useResearchTasks({
    sessionIdRef,
    ensurePendingMessage: ensurePendingResearchMessage,
    onTaskCompletedInActiveSession: handleTaskCompletedInActiveSession,
    onTaskFailedInActiveSession: handleTaskFailedInActiveSession,
    onTaskMissingInActiveSession: handleTaskFailedInActiveSession,
    onTaskProgressInActiveSession: handleTaskProgressInActiveSession,
    createClientMessageId,
    refreshSessions: () => refreshSessions({ silent: true }),
  });

  const activeSessionTask = sessionId ? taskBySession[sessionId] : null;
  const hasActiveResearchTaskForCurrentSession = isResearchTaskOngoing(activeSessionTask);
  const isGeneratingResponse = getSessionGenerating(chatState, sessionId || NEW_SESSION_KEY);
  const isInteractionLocked = chatLoading || isGeneratingResponse || hasActiveResearchTaskForCurrentSession;
  const showAgentActivity = isGeneratingResponse || hasActiveResearchTaskForCurrentSession;

  useEffect(() => {
    if (!currentUser) {
      hasAttemptedAutoOpenRef.current = false;
      return;
    }

    void refreshSessions({ silent: false });
  }, [currentUser, refreshSessions]);

  const loadChat = useCallback(
    async (selectedSessionId, { closeSidebarOnMobile = true } = {}) => {
      if (!selectedSessionId) return;

      try {
        dispatch({ type: 'LOAD_CHAT_START' });
        const { stale, payload } = await loadChatMessages(selectedSessionId, { timeoutMs: 30_000 });
        if (stale || !payload) return;

        const loadedMessages = Array.isArray(payload?.messages) ? payload.messages : [];
        loadedUserMessageIndexRef.current = findLastUserMessageIndex(loadedMessages);
        shouldScrollToLoadedUserMessageRef.current = true;

        dispatch({ type: 'LOAD_CHAT_SUCCESS', messages: loadedMessages });
        setSessionId(selectedSessionId);
        sessionIdRef.current = selectedSessionId;
        applyActiveTaskSnapshot(payload?.active_task, selectedSessionId);
        applySessionTitleFromList(sessions, selectedSessionId);

        if (closeSidebarOnMobile && window.innerWidth < 768) {
          setIsSidebarOpen(false);
        }

        acknowledgeTerminalTask(selectedSessionId);
      } catch (error) {
        console.error('Error loading chat:', error);
        shouldScrollToLoadedUserMessageRef.current = false;
        loadedUserMessageIndexRef.current = -1;
        dispatch({
          type: 'LOAD_CHAT_ERROR',
          message: error.message || 'Failed to load chat history.',
        });
      }
    },
    [
      acknowledgeTerminalTask,
      applyActiveTaskSnapshot,
      applySessionTitleFromList,
      loadChatMessages,
      sessions,
    ]
  );

  useEffect(() => {
    if (!currentUser) return;
    if (sessionsLoading) return;
    if (hasAttemptedAutoOpenRef.current) return;

    hasAttemptedAutoOpenRef.current = true;
    if (!AUTO_OPEN_RECENT_SESSION) return;
    if (sessionIdRef.current) return;
    if (!Array.isArray(sessions) || sessions.length === 0) return;

    void loadChat(sessions[0].id, { closeSidebarOnMobile: false });
  }, [currentUser, loadChat, sessions, sessionsLoading]);

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

  useEffect(() => {
    if (!shouldScrollToLoadedUserMessageRef.current || chatLoading) return;
    const container = chatScrollContainerRef.current;
    if (!container) return;

    let targetNode = null;
    const targetIndex = loadedUserMessageIndexRef.current;

    if (Number.isInteger(targetIndex) && targetIndex >= 0) {
      targetNode = container.querySelector(`[data-message-index="${targetIndex}"]`);
    }

    if (!targetNode) {
      const userNodes = container.querySelectorAll('[data-message-sender="user"]');
      if (userNodes.length > 0) {
        targetNode = userNodes[userNodes.length - 1];
      }
    }

    if (targetNode) {
      const containerRect = container.getBoundingClientRect();
      const targetRect = targetNode.getBoundingClientRect();
      const nextScrollTop = targetRect.top - containerRect.top + container.scrollTop - 12;
      container.scrollTop = Math.max(0, nextScrollTop);
    } else {
      container.scrollTop = container.scrollHeight;
    }

    shouldScrollToLoadedUserMessageRef.current = false;
    loadedUserMessageIndexRef.current = -1;
  }, [chatLoading, messages]);

  const updateChatSetting = (key, value) => {
    setChatSettings((prev) =>
      sanitizeChatSettings({
        ...prev,
        [key]: value,
      })
    );
  };

  const handleNewChat = () => {
    dispatch({ type: 'RESET_CHAT_VIEW' });
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
    shouldScrollToLoadedUserMessageRef.current = false;
    loadedUserMessageIndexRef.current = -1;
    hasAttemptedAutoOpenRef.current = true;
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
      const updated = await renameSession(renameSessionId, nextTitle);
      if (updated && renameSessionId === sessionIdRef.current) {
        setSessionTitle(updated.topic || nextTitle);
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
      await deleteSession(targetSessionId);
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
    setShareCollaborative(true);
    setShareError('');
    setIsShareModalOpen(true);
  };

  const closeShareModal = () => {
    setIsShareModalOpen(false);
    setShareError('');
    setShareEmail('');
    setShareSessionId(null);
    setShareSessionTitle('');
    setShareCollaborative(true);
  };

  const handleSend = async (event) => {
    event.preventDefault();
    if (chatLoading || hasActiveResearchTaskForCurrentSession || isGeneratingResponse) return;

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

    setComposerError('');
    closeCommandMenu();

    const pendingMessageId = `pending-${createClientMessageId()}`;
    const userMessageId = `user-${createClientMessageId()}`;
    const sendSessionKey = sessionIdRef.current || NEW_SESSION_KEY;

    dispatch({
      type: 'SEND_START',
      sessionId: sendSessionKey,
      userMessageId,
      userText: messageText,
      pendingMessageId,
    });

    setInput('');

    if (!sessionTitle) {
      setSessionTitle(deriveSessionTitle(messageText));
    }

    try {
      const activeSessionId = String(sessionIdRef.current || '').trim();
      const requestBody = {
        user_input: messageText,
        force_research: shouldForceResearch,
        model: chatSettings.model,
        research_breadth: chatSettings.research_breadth,
        research_depth: chatSettings.research_depth,
        document_length: chatSettings.document_length,
        ...(activeSessionId ? { session_id: activeSessionId } : {}),
      };

      const payload = await apiRequest('/chat', {
        method: 'POST',
        body: JSON.stringify(requestBody),
        timeoutMs: 600_000,
      });

      const responseKind = String(payload?.kind || '').trim().toLowerCase();
      const returnedSessionId = String(payload?.session_id || '').trim();
      const researchId = String(payload?.task?.id || '').trim();
      const responseText = String(payload?.message?.text || '').trim();

      if (returnedSessionId) {
        setSessionId(returnedSessionId);
        sessionIdRef.current = returnedSessionId;
      }

      if (responseKind === 'task' && researchId) {
        const targetSessionId = returnedSessionId || sessionIdRef.current;
        const normalizedPendingMessageId = pendingMessageId || getResearchPendingMessageId(researchId);
        const progressText = String(payload?.task?.progress_message || 'Research started. This may take a few minutes.');

        dispatch({
          type: 'TASK_QUEUED',
          sessionId: sendSessionKey,
          pendingMessageId: normalizedPendingMessageId,
          progressText,
        });

        upsertSessionTask(targetSessionId, {
          researchId,
          status: payload?.task?.status,
          pendingMessageId: normalizedPendingMessageId,
          currentNode: payload?.task?.current_node,
          progressMessage: payload?.task?.progress_message,
        });

        if (sessionIdRef.current === targetSessionId) {
          ensurePendingResearchMessage(normalizedPendingMessageId);
          dispatch({
            type: 'TASK_PROGRESS',
            sessionId: targetSessionId,
            pendingMessageId: normalizedPendingMessageId,
            progressText,
          });
        }

        await refreshSessions({ silent: true });
        return;
      }

      if (responseKind !== 'message' || !responseText) {
        throw new Error('Empty response from backend');
      }

      dispatch({
        type: 'SEND_SUCCESS',
        sessionId: sendSessionKey,
        pendingMessageId,
        responseText,
      });
      await refreshSessions({ silent: true });
    } catch (error) {
      console.error('Error sending message:', error);
      const errorText = String(error?.message || "Sorry, I couldn't process your request.");
      dispatch({
        type: 'SEND_ERROR',
        sessionId: sendSessionKey,
        pendingMessageId,
        errorText,
      });

      const normalizedError = errorText.toLowerCase();
      if (
        sessionIdRef.current &&
        (normalizedError.includes('already running') || normalizedError.includes('already in progress'))
      ) {
        await refreshActiveTaskForSession(sessionIdRef.current);
      }
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
          const nextCursor = applyCommandSuggestion(selected.command, composerRef.current);
          requestAnimationFrame(() => {
            const target = composerRef.current;
            if (!target) return;
            target.focus();
            if (typeof nextCursor === 'number') {
              target.setSelectionRange(nextCursor, nextCursor);
            }
          });
        }
        return;
      }
    }

    if (event.key !== 'Enter') return;
    if (event.shiftKey) return;

    event.preventDefault();
    if (isInteractionLocked || !input.trim()) return;
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
      await shareSession(targetSessionId, shareEmail.trim(), shareCollaborative);
      closeShareModal();
    } catch (error) {
      console.error('Sharing error:', error);
      setShareError(error.message || 'Failed to share chat');
    } finally {
      setShareLoading(false);
    }
  };

  const composerHint = hasActiveResearchTaskForCurrentSession
    ? 'A research task is in progress for this session. Sending is disabled until it completes.'
    : isGeneratingResponse
      ? 'Wait for the current response to finish before sending another message.'
      : 'Enter to send. Shift+Enter for a new line.';

  const sessionTaskStatusLabel = useMemo(() => {
    if (!hasActiveResearchTaskForCurrentSession) return '';
    const activeProgressMessage = String(activeSessionTask?.progressMessage || '').trim();
    if (activeProgressMessage) return activeProgressMessage;
    if (String(activeSessionTask?.status || '').toLowerCase() === 'queued') {
      return 'Research queued';
    }
    return 'Research running';
  }, [activeSessionTask?.progressMessage, activeSessionTask?.status, hasActiveResearchTaskForCurrentSession]);

  return (
    <ChatLayout>
      <ChatModals
        isRenameModalOpen={isRenameModalOpen}
        closeRenameModal={closeRenameModal}
        handleRenameSubmit={handleRenameSubmit}
        renameValue={renameValue}
        setRenameValue={setRenameValue}
        renameError={renameError}
        renameLoading={renameLoading}
        isShareModalOpen={isShareModalOpen}
        closeShareModal={closeShareModal}
        shareSessionTitle={shareSessionTitle}
        handleShareSubmit={handleShareSubmit}
        shareEmail={shareEmail}
        setShareEmail={setShareEmail}
        shareCollaborative={shareCollaborative}
        setShareCollaborative={setShareCollaborative}
        shareError={shareError}
        shareLoading={shareLoading}
      />

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
            taskBySession={taskBySession}
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
            taskBySession={taskBySession}
          />
        )}
      </aside>

      <main className="relative flex min-h-0 min-w-0 flex-1 flex-col pt-16">
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
              {showAgentActivity && (
                <span className="hidden items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 md:inline-flex">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-700 animate-pulse" />
                  {hasActiveResearchTaskForCurrentSession ? sessionTaskStatusLabel : 'Generating'}
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

        <MessageList
          chatLoading={chatLoading}
          messages={messages}
          isInteractionLocked={isInteractionLocked}
          quickPrompts={QUICK_PROMPTS}
          onQuickPromptSelect={setInput}
          chatScrollContainerRef={chatScrollContainerRef}
        />

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
                        disabled={isInteractionLocked}
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
                        disabled={isInteractionLocked}
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
                        disabled={isInteractionLocked}
                        className="rounded-lg border border-blue-100 bg-white px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                      >
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                    </label>
                    <label className="flex flex-col gap-1 rounded-xl border border-blue-100 bg-blue-50/30 px-2.5 py-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-blue-800">Document Length</span>
                      <select
                        value={chatSettings.document_length}
                        onChange={(event) => updateChatSetting('document_length', event.target.value)}
                        disabled={isInteractionLocked}
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
                  disabled={isInteractionLocked}
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
                        onClick={() => {
                          const nextCursor = applyCommandSuggestion(option.command, composerRef.current);
                          requestAnimationFrame(() => {
                            const target = composerRef.current;
                            if (!target) return;
                            target.focus();
                            if (typeof nextCursor === 'number') {
                              target.setSelectionRange(nextCursor, nextCursor);
                            }
                          });
                        }}
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
                  disabled={isInteractionLocked || !input.trim() || isEmptyResearchCommand}
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10.5 22 3l-7.5 19-2.8-8.7L3 10.5Z" />
                  </svg>
                  Send
                </button>
              </div>

              <div className="flex items-center justify-between px-2 pb-1 pt-2 text-[11px] text-slate-500">
                <span>{composerHint}</span>
                <span>
                  {sessionId
                    ? hasOngoingTaskForSession(sessionId)
                      ? 'Task active'
                      : 'Session active'
                    : hasAnyOngoingTask
                      ? 'Background tasks active'
                      : 'New session'}
                </span>
              </div>
              {composerError && (
                <p className="px-2 pb-1 text-xs text-red-600">{composerError}</p>
              )}
            </div>
          </form>
        </footer>
      </main>
    </ChatLayout>
  );
}
