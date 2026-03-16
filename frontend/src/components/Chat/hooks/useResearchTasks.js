import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest } from '../../../lib/api';
import { resolveResearchProgress } from '../researchProgress';

const BASE_POLL_INTERVAL_MS = 5_000;
const SLOW_POLL_INTERVAL_MS = 5_000;
const SLOW_POLL_AFTER_COUNT = 20;

const normalizeResearchStatus = (status) => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'queued' || normalized === 'running' || normalized === 'completed' || normalized === 'failed') {
    return normalized;
  }
  return 'failed';
};

const isOngoingStatus = (status) => status === 'queued' || status === 'running';
const normalizeNodeName = (value) => {
  const normalized = String(value || '').trim();
  return normalized || null;
};

export const getResearchPendingMessageId = (researchId) => `pending-research-${researchId}`;

const patchTaskEntry = (taskBySession, sessionId, patch) => ({
  ...taskBySession,
  [sessionId]: {
    ...(taskBySession[sessionId] || {}),
    ...patch,
  },
});

export function useResearchTasks({
  sessionIdRef,
  ensurePendingMessage,
  onTaskCompletedInActiveSession,
  onTaskFailedInActiveSession,
  onTaskMissingInActiveSession,
  onTaskProgressInActiveSession,
  createClientMessageId,
  refreshSessions,
}) {
  const [taskBySession, setTaskBySession] = useState({});
  const taskBySessionRef = useRef(taskBySession);
  const inFlightRef = useRef(new Set());

  useEffect(() => {
    taskBySessionRef.current = taskBySession;
  }, [taskBySession]);

  const upsertSessionTask = useCallback((sessionId, payload) => {
    if (!sessionId) return null;
    const researchId = String(payload?.researchId || '').trim();
    if (!researchId) return null;
    const status = normalizeResearchStatus(payload?.status);
    const currentNode = normalizeNodeName(payload?.currentNode);
    const { progressText: progressMessage, progressDetails } = resolveResearchProgress(
      status,
      currentNode,
      payload?.progressMessage,
      payload?.progressDetails
    );
    const pendingMessageId =
      String(payload?.pendingMessageId || '').trim() || getResearchPendingMessageId(researchId);
    const now = Date.now();

    setTaskBySession((prev) =>
      patchTaskEntry(prev, sessionId, {
        sessionId,
        researchId,
        pendingMessageId,
        status,
        currentNode,
        progressMessage,
        progressDetails,
        startedAt: Number(prev[sessionId]?.startedAt || now),
        pollCount: Number(prev[sessionId]?.pollCount || 0),
        nextPollAt: now,
        lastUpdatedAt: now,
      })
    );
    return { sessionId, researchId, pendingMessageId, status };
  }, []);

  const clearSessionTask = useCallback((sessionId) => {
    if (!sessionId) return;
    setTaskBySession((prev) => {
      if (!prev[sessionId]) return prev;
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
  }, []);

  const acknowledgeTerminalTask = useCallback((sessionId) => {
    const existing = taskBySessionRef.current[sessionId];
    if (!existing) return;
    if (isOngoingStatus(existing.status)) return;
    clearSessionTask(sessionId);
  }, [clearSessionTask]);

  const applyActiveTaskSnapshot = useCallback((activeTaskSnapshot, targetSessionId) => {
    const taskId = String(activeTaskSnapshot?.id || '').trim();
    const taskType = String(activeTaskSnapshot?.type || '').trim().toLowerCase();
    const taskStatus = normalizeResearchStatus(activeTaskSnapshot?.status);

    if (taskId && taskType === 'research' && isOngoingStatus(taskStatus)) {
      const current = taskBySessionRef.current[targetSessionId];
      const pendingMessageId =
        String(current?.pendingMessageId || '').trim() || getResearchPendingMessageId(taskId);
      upsertSessionTask(targetSessionId, {
        researchId: taskId,
        status: taskStatus,
        pendingMessageId,
        currentNode: activeTaskSnapshot?.current_node,
        progressMessage: activeTaskSnapshot?.progress_message,
        progressDetails: activeTaskSnapshot?.progress_details,
      });
      if (sessionIdRef.current === targetSessionId) {
        ensurePendingMessage?.(pendingMessageId);
        const currentTask = taskBySessionRef.current[targetSessionId];
        const { progressText, progressDetails } = resolveResearchProgress(
          taskStatus,
          normalizeNodeName(activeTaskSnapshot?.current_node),
          activeTaskSnapshot?.progress_message || currentTask?.progressMessage,
          activeTaskSnapshot?.progress_details || currentTask?.progressDetails
        );
        if (progressText) {
          onTaskProgressInActiveSession?.({
            sessionId: targetSessionId,
            researchId: taskId,
            pendingMessageId,
            progressText,
            progressDetails,
          });
        }
      }
      return true;
    }

    const existing = taskBySessionRef.current[targetSessionId];
    if (existing && isOngoingStatus(existing.status)) {
      clearSessionTask(targetSessionId);
    }
    return false;
  }, [
    clearSessionTask,
    ensurePendingMessage,
    onTaskProgressInActiveSession,
    sessionIdRef,
    upsertSessionTask,
  ]);

  const refreshActiveTaskForSession = useCallback(async (targetSessionId) => {
    if (!targetSessionId) return;
    try {
      const payload = await apiRequest(`/chat/sessions/${targetSessionId}/messages`, {
        method: 'GET',
        timeoutMs: 20_000,
      });
      applyActiveTaskSnapshot(payload?.active_task, targetSessionId);
    } catch (error) {
      if (error?.message === 'Request was cancelled.') return;
      console.error('Error refreshing active task:', error);
    }
  }, [applyActiveTaskSnapshot]);

  const ongoingTaskEntries = useMemo(
    () =>
      Object.values(taskBySession).filter((task) => {
        const sessionId = String(task?.sessionId || '').trim();
        return Boolean(sessionId) && isOngoingStatus(normalizeResearchStatus(task?.status));
      }),
    [taskBySession]
  );

  useEffect(() => {
    if (ongoingTaskEntries.length === 0) return undefined;

    let cancelled = false;
    const pollSingleTask = async (task) => {
      const sessionId = String(task?.sessionId || '').trim();
      const researchId = String(task?.researchId || '').trim();
      const pendingMessageId = String(task?.pendingMessageId || '').trim();
      if (!sessionId || !researchId) return;
      if (inFlightRef.current.has(researchId)) return;

      const currentTask = taskBySessionRef.current[sessionId];
      if (!currentTask || !isOngoingStatus(currentTask.status)) return;
      if (Number(currentTask.nextPollAt || 0) > Date.now()) return;

      inFlightRef.current.add(researchId);
      try {
        const taskPayload = await apiRequest(`/chat/tasks/${researchId}`, {
          method: 'GET',
          timeoutMs: 20_000,
        });
        if (cancelled) return;

        const status = normalizeResearchStatus(taskPayload?.status);
        const currentNode = normalizeNodeName(taskPayload?.current_node);
        const { progressText: progressMessage, progressDetails } = resolveResearchProgress(
          status,
          currentNode,
          taskPayload?.progress_message,
          taskPayload?.progress_details
        );
        if (isOngoingStatus(status)) {
          setTaskBySession((prev) => {
            const existing = prev[sessionId];
            if (!existing || existing.researchId !== researchId) return prev;
            const nextPollCount = Number(existing.pollCount || 0) + 1;
            const nextInterval =
              nextPollCount >= SLOW_POLL_AFTER_COUNT ? SLOW_POLL_INTERVAL_MS : BASE_POLL_INTERVAL_MS;
            return patchTaskEntry(prev, sessionId, {
              status,
              currentNode,
              progressMessage,
              progressDetails,
              pollCount: nextPollCount,
              nextPollAt: Date.now() + nextInterval,
              lastUpdatedAt: Date.now(),
            });
          });
          if (sessionIdRef.current === sessionId && progressMessage) {
            onTaskProgressInActiveSession?.({
              sessionId,
              researchId,
              pendingMessageId,
              progressText: progressMessage,
              progressDetails,
            });
          }
          return;
        }

        if (status === 'failed') {
          const failureText = String(taskPayload?.error || 'Research failed. Please try again.');
          setTaskBySession((prev) =>
            patchTaskEntry(prev, sessionId, {
              status: 'failed',
              currentNode,
              progressMessage,
              progressDetails,
              nextPollAt: null,
              lastUpdatedAt: Date.now(),
              failureText,
            })
          );
          if (sessionIdRef.current === sessionId) {
            onTaskFailedInActiveSession?.({
              sessionId,
              researchId,
              pendingMessageId,
              errorText: failureText,
              messageId: `ai-error-${createClientMessageId()}`,
            });
          }
          await refreshSessions?.();
          return;
        }

        const responseText = String(taskPayload?.result || '').trim();
        if (!responseText) {
          const missingText = 'Research completed but no response text was returned.';
          setTaskBySession((prev) =>
            patchTaskEntry(prev, sessionId, {
              status: 'failed',
              nextPollAt: null,
              lastUpdatedAt: Date.now(),
              failureText: missingText,
            })
          );
          if (sessionIdRef.current === sessionId) {
            onTaskFailedInActiveSession?.({
              sessionId,
              researchId,
              pendingMessageId,
              errorText: missingText,
              messageId: `ai-error-${createClientMessageId()}`,
            });
          }
          await refreshSessions?.();
          return;
        }

        setTaskBySession((prev) =>
            patchTaskEntry(prev, sessionId, {
              status: 'completed',
              currentNode,
              progressMessage,
              progressDetails,
              nextPollAt: null,
              lastUpdatedAt: Date.now(),
              resultPreview: responseText.slice(0, 220),
          })
        );
        if (sessionIdRef.current === sessionId) {
          onTaskCompletedInActiveSession?.({
            sessionId,
            researchId,
            pendingMessageId,
            responseText,
            messageId: `ai-${createClientMessageId()}`,
          });
        }
        await refreshSessions?.();
      } catch (error) {
        if (cancelled) return;
        const errorText = String(error?.message || '').toLowerCase();
        if (errorText.includes('not found')) {
          const message = 'Research task could not be found. Please retry.';
          setTaskBySession((prev) =>
            patchTaskEntry(prev, sessionId, {
              status: 'failed',
              nextPollAt: null,
              lastUpdatedAt: Date.now(),
              failureText: message,
            })
          );
          if (sessionIdRef.current === sessionId) {
            onTaskMissingInActiveSession?.({
              sessionId,
              researchId,
              pendingMessageId,
              errorText: message,
              messageId: `ai-error-${createClientMessageId()}`,
            });
          }
          return;
        }

        if (error?.message === 'Request was cancelled.') return;
        console.error('Error polling research status:', error);
        setTaskBySession((prev) => {
          const existing = prev[sessionId];
          if (!existing || existing.researchId !== researchId) return prev;
          const nextPollCount = Number(existing.pollCount || 0) + 1;
          const nextInterval =
            nextPollCount >= SLOW_POLL_AFTER_COUNT ? SLOW_POLL_INTERVAL_MS : BASE_POLL_INTERVAL_MS;
          return patchTaskEntry(prev, sessionId, {
            pollCount: nextPollCount,
            nextPollAt: Date.now() + nextInterval,
            lastUpdatedAt: Date.now(),
          });
        });
      } finally {
        inFlightRef.current.delete(researchId);
      }
    };

    const tick = () => {
      if (cancelled) return;
      const snapshot = Object.values(taskBySessionRef.current);
      snapshot.forEach((task) => {
        if (!isOngoingStatus(normalizeResearchStatus(task?.status))) return;
        void pollSingleTask(task);
      });
    };

    tick();
    const intervalId = window.setInterval(tick, BASE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [
    createClientMessageId,
    onTaskCompletedInActiveSession,
    onTaskFailedInActiveSession,
    onTaskMissingInActiveSession,
    onTaskProgressInActiveSession,
    ongoingTaskEntries.length,
    refreshSessions,
    sessionIdRef,
  ]);

  const hasAnyOngoingTask = useMemo(
    () => ongoingTaskEntries.length > 0,
    [ongoingTaskEntries.length]
  );

  const hasOngoingTaskForSession = useCallback((sessionId) => {
    const task = taskBySessionRef.current[String(sessionId || '').trim()];
    if (!task) return false;
    return isOngoingStatus(normalizeResearchStatus(task.status));
  }, []);

  return {
    taskBySession,
    upsertSessionTask,
    clearSessionTask,
    acknowledgeTerminalTask,
    applyActiveTaskSnapshot,
    refreshActiveTaskForSession,
    hasAnyOngoingTask,
    hasOngoingTaskForSession,
  };
}
