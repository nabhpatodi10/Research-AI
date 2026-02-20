export const NEW_SESSION_KEY = '__new__';

const defaultState = {
  messages: [],
  chatLoading: false,
  generatingBySession: {},
};

const replaceMessageById = (messages, messageId, nextMessage) => {
  const index = messages.findIndex((message) => message.id === messageId);
  if (index < 0) return messages;
  return messages.map((message, currentIndex) => (currentIndex === index ? nextMessage : message));
};

const sessionKeyForAction = (sessionId) => String(sessionId || NEW_SESSION_KEY);

export function getSessionGenerating(state, sessionId) {
  const sessionKey = sessionKeyForAction(sessionId);
  return Boolean(state.generatingBySession[sessionKey]);
}

export function chatReducer(state = defaultState, action) {
  switch (action.type) {
    case 'RESET_CHAT_VIEW':
      return {
        ...state,
        messages: [],
        chatLoading: false,
      };
    case 'LOAD_CHAT_START':
      return {
        ...state,
        chatLoading: true,
        messages: [],
      };
    case 'LOAD_CHAT_SUCCESS':
      return {
        ...state,
        chatLoading: false,
        messages: Array.isArray(action.messages) ? action.messages : [],
      };
    case 'LOAD_CHAT_ERROR':
      return {
        ...state,
        chatLoading: false,
        messages: [
          {
            id: 'system-error',
            text: String(action.message || 'Failed to load chat history.'),
            sender: 'ai-error',
            status: 'error',
          },
        ],
      };
    case 'SEND_START': {
      const sessionKey = sessionKeyForAction(action.sessionId);
      return {
        ...state,
        generatingBySession: {
          ...state.generatingBySession,
          [sessionKey]: true,
        },
        messages: [
          ...state.messages,
          {
            id: String(action.userMessageId),
            text: String(action.userText || ''),
            sender: 'user',
          },
          {
            id: String(action.pendingMessageId),
            text: '',
            sender: 'ai',
            status: 'pending',
          },
        ],
      };
    }
    case 'SEND_SUCCESS': {
      const sessionKey = sessionKeyForAction(action.sessionId);
      const nextMessages = state.messages.map((message) =>
        message.id === action.pendingMessageId
          ? { ...message, text: String(action.responseText || ''), sender: 'ai', status: 'done' }
          : message
      );
      return {
        ...state,
        generatingBySession: {
          ...state.generatingBySession,
          [sessionKey]: false,
        },
        messages: nextMessages,
      };
    }
    case 'SEND_ERROR': {
      const sessionKey = sessionKeyForAction(action.sessionId);
      const nextMessages = state.messages.map((message) =>
        message.id === action.pendingMessageId
          ? {
              ...message,
              text: String(action.errorText || "Sorry, I couldn't process your request."),
              sender: 'ai-error',
              status: 'error',
            }
          : message
      );
      return {
        ...state,
        generatingBySession: {
          ...state.generatingBySession,
          [sessionKey]: false,
        },
        messages: nextMessages,
      };
    }
    case 'TASK_QUEUED': {
      const sessionKey = sessionKeyForAction(action.sessionId);
      const queuedText = String(action.progressText || 'Research started. This may take a few minutes.');
      const nextMessages = state.messages.map((message) =>
        message.id === action.pendingMessageId
          ? {
              ...message,
              text: queuedText,
              sender: 'ai',
              status: 'pending',
            }
          : message
      );
      return {
        ...state,
        generatingBySession: {
          ...state.generatingBySession,
          [sessionKey]: false,
        },
        messages: nextMessages,
      };
    }
    case 'TASK_PROGRESS': {
      const progressText = String(action.progressText || '').trim();
      if (!progressText) return state;
      return {
        ...state,
        messages: state.messages.map((message) =>
          message.id === action.pendingMessageId && message.status === 'pending'
            ? {
                ...message,
                text: progressText,
                sender: 'ai',
                status: 'pending',
              }
            : message
        ),
      };
    }
    case 'TASK_DONE': {
      const sessionKey = sessionKeyForAction(action.sessionId);
      const responseText = String(action.responseText || '').trim();
      if (!responseText) {
        return {
          ...state,
          generatingBySession: {
            ...state.generatingBySession,
            [sessionKey]: false,
          },
        };
      }

      const pendingIndex = state.messages.findIndex((message) => message.id === action.pendingMessageId);
      if (pendingIndex >= 0) {
        return {
          ...state,
          generatingBySession: {
            ...state.generatingBySession,
            [sessionKey]: false,
          },
          messages: replaceMessageById(state.messages, action.pendingMessageId, {
            ...state.messages[pendingIndex],
            text: responseText,
            sender: 'ai',
            status: 'done',
          }),
        };
      }

      const lastMessage = state.messages[state.messages.length - 1];
      const isDuplicateAssistantMessage =
        lastMessage?.sender === 'ai' && String(lastMessage?.text || '').trim() === responseText;
      if (isDuplicateAssistantMessage) {
        return {
          ...state,
          generatingBySession: {
            ...state.generatingBySession,
            [sessionKey]: false,
          },
        };
      }

      return {
        ...state,
        generatingBySession: {
          ...state.generatingBySession,
          [sessionKey]: false,
        },
        messages: [
          ...state.messages,
          {
            id: String(action.messageId || ''),
            text: responseText,
            sender: 'ai',
            status: 'done',
          },
        ],
      };
    }
    case 'TASK_FAILED': {
      const sessionKey = sessionKeyForAction(action.sessionId);
      const errorText = String(action.errorText || 'Research failed. Please try again.');
      const hasPending = state.messages.some((message) => message.id === action.pendingMessageId);

      return {
        ...state,
        generatingBySession: {
          ...state.generatingBySession,
          [sessionKey]: false,
        },
        messages: hasPending
          ? state.messages.map((message) =>
              message.id === action.pendingMessageId
                ? { ...message, text: errorText, sender: 'ai-error', status: 'error' }
                : message
            )
          : [
              ...state.messages,
              {
                id: String(action.messageId || ''),
                text: errorText,
                sender: 'ai-error',
                status: 'error',
              },
            ],
      };
    }
    case 'ADD_PENDING_RESEARCH_MESSAGE': {
      const pendingMessageId = String(action.pendingMessageId || '').trim();
      if (!pendingMessageId) return state;
      const alreadyPresent = state.messages.some((message) => message.id === pendingMessageId);
      if (alreadyPresent) return state;
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: pendingMessageId,
            text: 'Research is in progress. Final document will appear here once complete.',
            sender: 'ai',
            status: 'pending',
          },
        ],
      };
    }
    default:
      return state;
  }
}

export const initialChatState = defaultState;
