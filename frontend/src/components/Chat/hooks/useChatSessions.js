import { useCallback, useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../../lib/api';

export function useChatSessions() {
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState('');

  const sessionsRequestRef = useRef({ requestId: 0, controller: null });
  const chatRequestRef = useRef({ requestId: 0, controller: null });

  useEffect(
    () => () => {
      sessionsRequestRef.current.controller?.abort();
      chatRequestRef.current.controller?.abort();
    },
    []
  );

  const loadSessions = useCallback(async ({ silent = false, activeSessionId, onApplySessionTitle } = {}) => {
    const requestId = sessionsRequestRef.current.requestId + 1;
    sessionsRequestRef.current.requestId = requestId;
    sessionsRequestRef.current.controller?.abort();
    const controller = new AbortController();
    sessionsRequestRef.current.controller = controller;

    if (!silent) setSessionsLoading(true);
    try {
      const payload = await apiRequest('/chat/sessions', {
        method: 'GET',
        signal: controller.signal,
        timeoutMs: 20_000,
      });
      if (sessionsRequestRef.current.requestId !== requestId) return null;

      const loadedSessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
      setSessions(loadedSessions);
      setSessionsError('');
      if (activeSessionId && typeof onApplySessionTitle === 'function') {
        onApplySessionTitle(loadedSessions, activeSessionId);
      }
      return loadedSessions;
    } catch (error) {
      if (sessionsRequestRef.current.requestId !== requestId) return null;
      if (error?.message === 'Request was cancelled.') return null;
      setSessionsError(error.message || 'Failed to load chat history');
      return null;
    } finally {
      if (!silent && sessionsRequestRef.current.requestId === requestId) {
        setSessionsLoading(false);
      }
      if (sessionsRequestRef.current.requestId === requestId) {
        sessionsRequestRef.current.controller = null;
      }
    }
  }, []);

  const loadChatMessages = useCallback(async (sessionId, { timeoutMs = 30_000 } = {}) => {
    const requestId = chatRequestRef.current.requestId + 1;
    chatRequestRef.current.requestId = requestId;
    chatRequestRef.current.controller?.abort();
    const controller = new AbortController();
    chatRequestRef.current.controller = controller;

    try {
      const payload = await apiRequest(`/chat/sessions/${sessionId}/messages`, {
        method: 'GET',
        signal: controller.signal,
        timeoutMs,
      });
      if (chatRequestRef.current.requestId !== requestId) {
        return { stale: true, payload: null };
      }
      return { stale: false, payload };
    } catch (error) {
      if (chatRequestRef.current.requestId !== requestId) {
        return { stale: true, payload: null };
      }
      if (error?.message === 'Request was cancelled.') {
        return { stale: true, payload: null };
      }
      throw error;
    } finally {
      if (chatRequestRef.current.requestId === requestId) {
        chatRequestRef.current.controller = null;
      }
    }
  }, []);

  const renameSession = useCallback(async (sessionId, topic) => {
    const payload = await apiRequest(`/chat/sessions/${sessionId}`, {
      method: 'PATCH',
      body: JSON.stringify({ topic }),
      timeoutMs: 20_000,
    });
    const updated = payload?.session;
    if (updated) {
      setSessions((prev) => prev.map((session) => (session.id === updated.id ? { ...session, ...updated } : session)));
    }
    return updated || null;
  }, []);

  const deleteSession = useCallback(async (sessionId) => {
    await apiRequest(`/chat/sessions/${sessionId}`, { method: 'DELETE', timeoutMs: 20_000 });
    setSessions((prev) => prev.filter((session) => session.id !== sessionId));
  }, []);

  const shareSession = useCallback(async (sessionId, email, collaborative = true) => {
    const payload = await apiRequest(`/chat/sessions/${sessionId}/share`, {
      method: 'POST',
      body: JSON.stringify({ email, collaborative }),
      timeoutMs: 20_000,
    });
    return {
      ok: Boolean(payload?.ok),
      mode: String(payload?.mode || (collaborative ? 'collaborative' : 'snapshot')),
      sharedSessionId: String(payload?.shared_session_id || '').trim() || sessionId,
    };
  }, []);

  return {
    sessions,
    setSessions,
    sessionsLoading,
    setSessionsLoading,
    sessionsError,
    setSessionsError,
    loadSessions,
    loadChatMessages,
    renameSession,
    deleteSession,
    shareSession,
  };
}
