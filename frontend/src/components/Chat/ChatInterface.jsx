import { useState, useEffect, Fragment, useRef } from 'react';
import { doc, getDoc, setDoc, updateDoc, deleteField, collection, query, where, getDocs } from 'firebase/firestore';
import { db } from '../../firebase';
import { useAuth } from '../../context/AuthContext';
import ChatHistory from './ChatHistory';
import MarkdownRenderer from './MarkdownRenderer';
import { Dialog, Transition } from '@headlessui/react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const createClientSessionId = () => {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return uuid;
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const deriveSessionTitle = (text) => {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (!normalized) return 'Untitled Session';
  const maxLength = 72;
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 3)}...` : normalized;
};

const extractTextFromContent = (content) => {
  if (typeof content === 'string') {
    return content;
  }

  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === 'string') return item;
        if (!item || typeof item !== 'object') return '';
        if (item.type === 'text' && typeof item.text === 'string') return item.text;
        return extractTextFromContent(item);
      })
      .filter((text) => typeof text === 'string' && text.trim())
      .join('\n');
  }

  if (!content || typeof content !== 'object') {
    return '';
  }

  if (typeof content.text === 'string') {
    return content.text;
  }

  if (typeof content.content === 'string') {
    return content.content;
  }

  if (Array.isArray(content.content)) {
    return extractTextFromContent(content.content);
  }

  if (Array.isArray(content.blocks)) {
    return extractTextFromContent(content.blocks);
  }

  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return '';
  }
};

const normalizeStoredMessage = (rawMessage, index) => {
  let parsedMessage = rawMessage;
  if (typeof rawMessage === 'string') {
    const trimmed = rawMessage.trim();
    if (!trimmed) return null;
    try {
      parsedMessage = JSON.parse(trimmed);
    } catch {
      return null;
    }
  }

  if (!parsedMessage || typeof parsedMessage !== 'object') return null;

  const typeToken = String(parsedMessage.type || parsedMessage.role || '').toLowerCase();
  const isHuman = typeToken.includes('human') || typeToken === 'user';
  const isAi = typeToken.includes('ai') || typeToken.includes('assistant');
  if (!isHuman && !isAi) return null;

  const content = parsedMessage.content ?? parsedMessage.data?.content;
  const text = extractTextFromContent(content).trim();
  if (!text) return null;

  return {
    id: `msg-${index}`,
    text,
    sender: isHuman ? 'user' : 'ai',
  };
};

const SidebarContent = ({
  searchTerm,
  setSearchTerm,
  handleNewChat,
  handleDeleteChat,
  handleRenameChat,
  handleShareChat,
  loadChat,
}) => (
  <>
    <div className="p-4 border-b border-gray-200">
      <h1 className="text-xl font-bold text-blue-900">ResearchAI</h1>
    </div>
    <div className="p-4 pb-32 overflow-y-scroll no-scrollbar h-full">
      <div className="mb-4">
        <input
          type="text"
          placeholder="Search chats..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          onTouchStart={(e) => e.stopPropagation()}
          className="w-full p-2 border border-gray-300 rounded text-sm"
        />
      </div>
      <div className="space-y-2">
        <button
          onClick={handleNewChat}
          className="w-full text-left p-2 hover:bg-gray-100 rounded text-sm font-medium hover:text-blue-900"
        >
          + New Chat
        </button>
        <ChatHistory
          onChatSelect={loadChat}
          onDeleteChat={handleDeleteChat}
          onRenameChat={handleRenameChat}
          onShareChat={handleShareChat}
          searchTerm={searchTerm}
        />
      </div>
    </div>
  </>
);

export default function ChatInterface() {
  const { currentUser } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isGeneratingResponse, setIsGeneratingResponse] = useState(false);
  const [sessionTitle, setSessionTitle] = useState('');
  const [sessionId, setSessionId] = useState(null);
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
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => window.innerWidth >= 768);
  const [searchTerm, setSearchTerm] = useState('');
  const sessionIdRef = useRef(null);
  const sessionTitleRef = useRef('');
  const isGeneratingRef = useRef(false);

  useEffect(() => {
    const saveChatSession = async () => {
      if (!currentUser || !sessionId) return;

      const userChatsRef = doc(db, 'user_chats', currentUser.uid);
      await setDoc(userChatsRef, {
        sessions: {
          [sessionId]: {
            topic: sessionTitle || 'Untitled Session',
            createdAt: new Date(),
          },
        },
      }, { merge: true });
    };

    saveChatSession();
  }, [sessionId, currentUser, sessionTitle]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    sessionTitleRef.current = sessionTitle;
  }, [sessionTitle]);

  const handleNewChat = () => {
    setMessages([]);
    setInput('');
    setSessionTitle('');
    setSessionId(null);
    sessionIdRef.current = null;
    sessionTitleRef.current = '';
    setIsRenameModalOpen(false);
    setRenameSessionId(null);
    setRenameValue('');
    setRenameError('');
    setShareError('');
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

  const handleRenameSubmit = async (e) => {
    e.preventDefault();
    if (!currentUser || !renameSessionId) return;

    const nextTitle = renameValue.trim();
    if (!nextTitle) {
      setRenameError('Chat name is required');
      return;
    }

    setRenameLoading(true);
    setRenameError('');
    try {
      const userChatsRef = doc(db, 'user_chats', currentUser.uid);
      const userChatsSnap = await getDoc(userChatsRef);
      const sessions = userChatsSnap.exists() ? (userChatsSnap.data().sessions || {}) : {};
      const existing = sessions[renameSessionId] || {};

      await setDoc(userChatsRef, {
        sessions: {
          [renameSessionId]: {
            ...existing,
            topic: nextTitle,
            createdAt: existing.createdAt || new Date(),
          },
        },
      }, { merge: true });

      if (renameSessionId === sessionId) {
        sessionTitleRef.current = nextTitle;
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
    if (!currentUser || !targetSessionId) return;

    const shouldDelete = window.confirm(`Delete chat "${targetTitle}"?`);
    if (!shouldDelete) return;

    try {
      const userChatsRef = doc(db, 'user_chats', currentUser.uid);
      await updateDoc(userChatsRef, {
        [`sessions.${targetSessionId}`]: deleteField(),
      });

      if (targetSessionId === sessionId) {
        handleNewChat();
      }
    } catch (error) {
      console.error('Error deleting chat:', error);
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

  const handleSend = async (e) => {
    e.preventDefault();
    const messageText = input.trim();
    if (!messageText || loading || isGeneratingRef.current) return;

    isGeneratingRef.current = true;
    setIsGeneratingResponse(true);

    let activeSessionId = sessionIdRef.current;
    if (!activeSessionId) {
      activeSessionId = createClientSessionId();
      sessionIdRef.current = activeSessionId;
      setSessionId(activeSessionId);
    }

    let nextSessionTitle = sessionTitleRef.current;
    if (!nextSessionTitle) {
      nextSessionTitle = deriveSessionTitle(messageText);
      sessionTitleRef.current = nextSessionTitle;
      setSessionTitle(nextSessionTitle);
    }

    const pendingMessageId = `pending-${createClientSessionId()}`;
    setMessages((prev) => [
      ...prev,
      { id: `user-${createClientSessionId()}`, text: messageText, sender: 'user' },
      { id: pendingMessageId, text: '', sender: 'ai', status: 'pending' },
    ]);
    setInput('');

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_input: messageText,
          session_id: activeSessionId,
        }),
      });

      if (!response.ok) throw new Error('Chat request failed');

      const data = await response.json();
      const responseText = String(data.response || '').trim();
      if (!responseText) throw new Error('Empty response from backend');

      setMessages((prev) => prev.map((message) => (
        message.id === pendingMessageId
          ? { ...message, text: responseText, sender: 'ai', status: 'done' }
          : message
      )));
    } catch (err) {
      console.error('Error sending message:', err);
      setMessages((prev) => prev.map((message) => (
        message.id === pendingMessageId
          ? { ...message, text: "Sorry, I couldn't process your request.", sender: 'ai-error', status: 'error' }
          : message
      )));
    } finally {
      isGeneratingRef.current = false;
      setIsGeneratingResponse(false);
    }
  };

  const loadChat = async (selectedSessionId) => {
    try {
      setLoading(true);
      setMessages([]);

      const userChatsRef = doc(db, 'user_chats', currentUser.uid);
      const userChatsSnap = await getDoc(userChatsRef);
      if (!userChatsSnap.exists()) throw new Error('No chat sessions found');

      const sessions = userChatsSnap.data().sessions || {};
      const rawSessionData = sessions[selectedSessionId];
      const resolvedSessionTitle = rawSessionData?.topic || 'Untitled Session';

      const sessionRef = doc(db, 'chats', selectedSessionId);
      const sessionSnap = await getDoc(sessionRef);
      if (!sessionSnap.exists()) throw new Error('Chat session not found');

      const messagesData = sessionSnap.data().messages || [];
      const processedMessages = messagesData
        .map((msg, index) => normalizeStoredMessage(msg, index))
        .filter((msg) => msg !== null);

      setSessionId(selectedSessionId);
      setSessionTitle(resolvedSessionTitle);
      sessionIdRef.current = selectedSessionId;
      sessionTitleRef.current = resolvedSessionTitle;
      setMessages(processedMessages);
    } catch (error) {
      console.error('Error loading chat:', error);
      setMessages([{
        text: 'Failed to load chat history. Please try again.',
        sender: 'system-error',
      }]);
    } finally {
      setLoading(false);
    }
  };

  const Message = ({ msg }) => {
    if (msg.status === 'pending') {
      return (
        <div className="max-w-full md:max-w-[75%] p-3 rounded-lg bg-white border border-gray-200">
          <div className="flex items-center gap-1 text-gray-600">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.2s]" />
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.1s]" />
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-bounce" />
          </div>
        </div>
      );
    }

    return (
      <div
        className={`max-w-full md:max-w-[75%] p-3 rounded-lg ${
          msg.sender === 'user'
            ? 'bg-blue-900 text-white'
            : msg.sender === 'ai'
            ? 'bg-white border border-gray-200'
            : msg.sender === 'system-error'
            ? 'bg-red-100 border border-red-200 text-red-700'
            : 'bg-gray-100 border border-gray-200'
        }`}
      >
        {msg.sender === 'ai' || msg.sender === 'ai-error' ? (
          <MarkdownRenderer content={msg.text} />
        ) : (
          <div className="whitespace-pre-wrap">{msg.text}</div>
        )}
      </div>
    );
  };

  const handleShareClick = () => {
    if (!sessionId) return;
    handleShareChat(sessionId, sessionTitle || 'Untitled Session');
  };

  const handleShareSubmit = async (e) => {
    e.preventDefault();
    setShareLoading(true);
    setShareError('');

    try {
      const targetSessionId = shareSessionId || sessionId;
      const targetSessionTitle = shareSessionTitle || sessionTitle || 'Untitled Session';
      if (!targetSessionId) {
        throw new Error('No chat selected to share');
      }

      const usersRef = collection(db, 'users');
      const q = query(usersRef, where('email', '==', shareEmail));
      const querySnapshot = await getDocs(q);

      if (querySnapshot.empty) {
        throw new Error('User not found');
      }

      const userDoc = querySnapshot.docs[0];
      const targetUserId = userDoc.id;

      const targetUserChatsRef = doc(db, 'user_chats', targetUserId);
      await setDoc(targetUserChatsRef, {
        sessions: {
          [targetSessionId]: {
            topic: targetSessionTitle,
            createdAt: new Date(),
            sharedBy: currentUser.email,
            isShared: true,
          },
        },
      }, { merge: true });

      setIsShareModalOpen(false);
      setShareEmail('');
      setShareSessionId(null);
      setShareSessionTitle('');
    } catch (error) {
      console.error('Sharing error:', error);
      setShareError(error.message || 'Failed to share chat');
    } finally {
      setShareLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-100 overflow-x-hidden">
      <Transition appear show={isRenameModalOpen} as={Fragment}>
        <Dialog as="div" className="relative z-10" onClose={closeRenameModal}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-opacity-25" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4 text-center">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all">
                  <Dialog.Title className="text-lg font-medium leading-6 text-gray-900">
                    Rename Chat Session
                  </Dialog.Title>

                  <form onSubmit={handleRenameSubmit} className="mt-4 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700">
                        Chat Name
                      </label>
                      <input
                        type="text"
                        required
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        className="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                      />
                    </div>

                    {renameError && (
                      <p className="text-red-500 text-sm">{renameError}</p>
                    )}

                    <div className="flex justify-end space-x-4">
                      <button
                        type="button"
                        onClick={closeRenameModal}
                        className="inline-flex justify-center rounded-md border border-transparent bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 focus:outline-none"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={renameLoading || !renameValue.trim()}
                        className="inline-flex justify-center rounded-md border border-transparent bg-blue-900 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none disabled:opacity-50"
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
        <Dialog as="div" className="relative z-10" onClose={closeShareModal}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-opacity-25" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4 text-center">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all">
                  <Dialog.Title className="text-lg font-medium leading-6 text-gray-900">
                    Share Chat Session
                  </Dialog.Title>

                  <form onSubmit={handleShareSubmit} className="mt-4 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700">
                        Recipient Email
                      </label>
                      <input
                        type="email"
                        required
                        value={shareEmail}
                        onChange={(e) => setShareEmail(e.target.value)}
                        className="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                      />
                    </div>

                    {shareError && (
                      <p className="text-red-500 text-sm">{shareError}</p>
                    )}

                    <div className="flex justify-end space-x-4">
                      <button
                        type="button"
                        onClick={closeShareModal}
                        className="inline-flex justify-center rounded-md border border-transparent bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 focus:outline-none"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={shareLoading}
                        className="inline-flex justify-center rounded-md border border-transparent bg-blue-900 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none disabled:opacity-50"
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

      <div className={`fixed inset-0 z-40 flex md:hidden ${isSidebarOpen ? '' : 'pointer-events-none'}`}>
        <div
          className={`fixed inset-0 bg-opacity-25 transition-opacity ${isSidebarOpen ? 'opacity-100' : 'opacity-0'}`}
          onClick={() => setIsSidebarOpen(false)}
        />
        <div
          className={`relative w-64 bg-white border-r border-gray-200 transform transition-transform ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
        >
          <SidebarContent
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

      <div
        className={`hidden md:flex md:flex-col bg-white border-r border-gray-200 pt-16 transition-all duration-300 ${isSidebarOpen ? 'md:w-64' : 'md:w-0 md:overflow-hidden'}`}
      >
        {isSidebarOpen && (
          <SidebarContent
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            handleNewChat={handleNewChat}
            handleDeleteChat={handleDeleteChat}
            handleRenameChat={handleRenameChat}
            handleShareChat={handleShareChat}
            loadChat={loadChat}
          />
        )}
      </div>

      <div className="flex-1 flex flex-col pt-16">
        <div className="p-4 border-b border-gray-200 bg-white flex items-center justify-between">
          <div className="flex items-center">
            <button
              className="md:hidden mr-2"
              onClick={() => setIsSidebarOpen(true)}
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16"></path>
              </svg>
            </button>
            <button
              className="hidden md:block mr-2"
              onClick={() => setIsSidebarOpen((v) => !v)}
            >
              <svg
                className="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                xmlns="http://www.w3.org/2000/svg"
              >
                {isSidebarOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 12L6 6V18Z" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 6h12M6 12h12M6 18h12" />
                )}
              </svg>
            </button>
            <h2 className="text-lg font-semibold text-blue-900">
              {sessionId ? `Chat: ${sessionTitle || 'Untitled Session'}` : 'New Chat'}
            </h2>
          </div>
          {sessionId && (
            <button
              onClick={handleShareClick}
              className="px-3 py-1 text-sm bg-blue-900 text-white rounded hover:bg-blue-700"
            >
              Share
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 pb-24">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <h3 className="text-xl font-medium">Start a New Chat</h3>
                <p className="text-gray-600 text-sm">Describe your research request in the message box below.</p>
              </div>
            </div>
          ) : (
            messages.map((msg, index) => (
              <div
                key={msg.id || index}
                className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <Message msg={msg} />
              </div>
            ))
          )}
        </div>

        <div className="sticky bottom-0 p-4 border-t border-gray-200 bg-white">
          <form onSubmit={handleSend} className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={sessionId ? 'Ask a follow-up question...' : 'Describe what you want to research...'}
              className="flex-1 p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              disabled={loading || isGeneratingResponse}
            />
            <button
              type="submit"
              className="px-4 py-2 bg-blue-900 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
              disabled={loading || isGeneratingResponse || !input.trim()}
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
