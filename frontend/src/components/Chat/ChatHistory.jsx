import { useState, useEffect } from 'react';
import { doc, onSnapshot } from 'firebase/firestore';
import { db } from '../../firebase';
import { useAuth } from '../../context/AuthContext';

export default function ChatHistory({
  onChatSelect,
  onDeleteChat,
  onRenameChat,
  onShareChat,
  searchTerm = '',
}) {
  const { currentUser } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [openMenuId, setOpenMenuId] = useState(null);

  useEffect(() => {
    if (!currentUser) return;

    const unsubscribe = onSnapshot(
      doc(db, 'user_chats', currentUser.uid),
      (doc) => {
        try {
          if (doc.exists()) {
            const sessionsData = doc.data().sessions || {};
            const sessionsArray = Object.entries(sessionsData).map(([id, session]) => ({
              id,
              topic: session?.topic || 'Untitled Session',
              createdAt: session?.createdAt?.toDate?.() || new Date(),
              isShared: session?.isShared || false,
              sharedBy: session?.sharedBy || null
            })).sort((a, b) => b.createdAt - a.createdAt);
            setSessions(sessionsArray);
            setError(null);
          } else {
            setSessions([]);
          }
        } catch (err) {
          console.error("Error processing sessions:", err);
          setError("Failed to load chat history");
        } finally {
          setLoading(false);
        }
      },
      (error) => {
        console.error("Firestore error:", error);
        setError("Connection error loading chats");
        setLoading(false);
      }
    );

    return () => unsubscribe();
  }, [currentUser]);

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

  const filtered = sessions.filter((s) =>
    s.topic.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) return <div className="text-gray-500 p-2">Loading history...</div>;
  if (error) return <div className="text-red-500 p-2">{error}</div>;
  if (filtered.length === 0) return <div className="text-gray-500 p-2">No previous chats</div>;

  return (
    <div className="space-y-2">
      {filtered.map((session) => (
        <div
          key={session.id}
          role="button"
          tabIndex={0}
          data-chat-menu-root="true"
          onClick={() => onChatSelect(session.id)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onChatSelect(session.id);
            }
          }}
          className="group relative w-full text-left p-2 hover:bg-gray-100 hover:text-blue-900 rounded text-sm transition-colors cursor-pointer"
        >
          <div className="flex items-start justify-between gap-2 pr-8">
            <div className="font-medium truncate">
              {session.topic}
            </div>
          </div>

          <button
            type="button"
            aria-label="Chat options"
            className={`absolute right-2 top-2 h-6 w-6 rounded flex items-center justify-center text-gray-600 hover:bg-gray-200 ${
              openMenuId === session.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
            }`}
            onClick={(event) => {
              event.stopPropagation();
              setOpenMenuId((prev) => (prev === session.id ? null : session.id));
            }}
          >
            <span className="text-base leading-none">⋮</span>
          </button>

          {openMenuId === session.id && (
            <div className="absolute right-2 top-8 z-20 min-w-36 rounded border border-gray-200 bg-white shadow-md overflow-hidden">
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-gray-100"
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
                className="block w-full px-3 py-2 text-left text-sm hover:bg-gray-100"
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

          <div>
            {session.isShared && (
                <span className="text-xs text-gray-500">Shared by {session.sharedBy}</span>
            )}
          </div>
          <div className="text-xs text-gray-500">
            {session.createdAt.toLocaleDateString()}
          </div>
        </div>
      ))}
    </div>
  );
}
