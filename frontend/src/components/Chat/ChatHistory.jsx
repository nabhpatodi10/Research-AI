import { useState, useEffect } from 'react';
import { doc, onSnapshot } from 'firebase/firestore';
import { db } from '../../firebase';
import { useAuth } from '../../context/AuthContext';

export default function ChatHistory({ onChatSelect, searchTerm = ''}) {
  const { currentUser } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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
              topic: typeof session === 'string' ? session : 
                    (session.topic || 'Untitled Session'),
              createdAt: session.createdAt?.toDate?.() || new Date(),
              isShared: session.isShared || false,
              sharedBy: session.sharedBy || null
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

  const filtered = sessions.filter((s) =>
    s.topic.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) return <div className="text-gray-500 p-2">Loading history...</div>;
  if (error) return <div className="text-red-500 p-2">{error}</div>;
  if (filtered.length === 0) return <div className="text-gray-500 p-2">No previous chats</div>;

  return (
    <div className="space-y-2">
      {filtered.map((session) => (
        <button
          key={session.id}
          onClick={() => onChatSelect(session.id)}
          className="w-full text-left p-2 hover:bg-gray-100 hover:text-blue-900 rounded text-sm transition-colors"
        >
          <div className="font-medium truncate">
            {session.topic}
          </div>
          <div>
            {session.isShared && (
                <span className="text-xs text-gray-500">Shared by {session.sharedBy}</span>
            )}
          </div>
          <div className="text-xs text-gray-500">
            {session.createdAt.toLocaleDateString()}
          </div>
        </button>
      ))}
    </div>
  );
}