import { useEffect, useMemo, useState } from 'react';

export default function ChatHistory({
  sessions = [],
  loading = false,
  error = null,
  activeSessionId = null,
  onChatSelect,
  onDeleteChat,
  onRenameChat,
  onShareChat,
  searchTerm = '',
}) {
  const [openMenuId, setOpenMenuId] = useState(null);

  useEffect(() => {
    if (!openMenuId) return undefined;

    const handleDocumentClick = (event) => {
      const menuRoot = event.target.closest('[data-chat-menu-root="true"]');
      if (!menuRoot) {
        setOpenMenuId(null);
      }
    };

    document.addEventListener('click', handleDocumentClick);
    return () => document.removeEventListener('click', handleDocumentClick);
  }, [openMenuId]);

  const filtered = useMemo(() => {
    const normalizedQuery = searchTerm.trim().toLowerCase();
    if (!normalizedQuery) return sessions;
    return sessions.filter((session) =>
      String(session.topic || 'Untitled Session').toLowerCase().includes(normalizedQuery)
    );
  }, [sessions, searchTerm]);

  if (loading) {
    return (
      <div className="space-y-2 p-1">
        {[1, 2, 3].map((row) => (
          <div key={row} className="animate-pulse rounded-xl border border-blue-100 bg-white/90 p-3">
            <div className="h-3 w-2/3 rounded bg-blue-100" />
            <div className="mt-2 h-2.5 w-1/3 rounded bg-blue-50" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-600">{error}</div>;
  }

  if (filtered.length === 0) {
    return <div className="rounded-lg border border-blue-100 bg-white/90 p-2 text-sm text-slate-500">No previous chats</div>;
  }

  return (
    <div className="space-y-2">
      {filtered.map((session) => {
        const createdAtText = session.createdAt
          ? new Date(session.createdAt).toLocaleString([], {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })
          : '';
        const isActive = activeSessionId === session.id;

        return (
          <div
            key={session.id}
            role="button"
            tabIndex={0}
            data-chat-menu-root="true"
            onClick={() => onChatSelect?.(session.id)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onChatSelect?.(session.id);
              }
            }}
            className={`group relative w-full cursor-pointer rounded-xl border p-3 text-left text-sm transition ${
              isActive
                ? 'border-blue-200 bg-blue-50/80 text-blue-900 shadow-sm'
                : 'border-blue-100 bg-white/90 text-slate-700 hover:border-blue-200 hover:bg-blue-50/40'
            }`}
          >
            <div className="flex items-start justify-between gap-2 pr-8">
              <p className="font-semibold leading-5 break-words">{session.topic || 'Untitled Session'}</p>
            </div>

            <button
              type="button"
              aria-label="Chat options"
              className={`absolute right-2 top-2 h-6 w-6 rounded-md flex items-center justify-center text-slate-500 hover:bg-blue-100 hover:text-blue-900 ${
                openMenuId === session.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
              }`}
              onClick={(event) => {
                event.stopPropagation();
                setOpenMenuId((prev) => (prev === session.id ? null : session.id));
              }}
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="5" r="2" />
                <circle cx="12" cy="12" r="2" />
                <circle cx="12" cy="19" r="2" />
              </svg>
            </button>

            {openMenuId === session.id && (
              <div className="absolute right-2 top-8 z-20 min-w-36 overflow-hidden rounded-xl border border-blue-100 bg-white shadow-lg">
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-blue-50"
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenMenuId(null);
                    onShareChat?.(session.id, session.topic);
                  }}
                >
                  Share chat
                </button>
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-blue-50"
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenMenuId(null);
                    onRenameChat?.(session.id, session.topic);
                  }}
                >
                  Rename chat
                </button>
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenMenuId(null);
                    onDeleteChat?.(session.id, session.topic);
                  }}
                >
                  Delete chat
                </button>
              </div>
            )}

            <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
              <span className="truncate">
                {session.isShared ? `Shared by ${session.sharedBy || 'unknown'}` : 'Private chat'}
              </span>
              <span>{createdAtText}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
