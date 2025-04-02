import { useState, useEffect } from 'react';
import { collection, query, where, orderBy, onSnapshot } from 'firebase/firestore';
import { db } from '../../firebase';
import { useAuth } from '../../context/AuthContext';

export default function ChatHistory() {
  const { currentUser } = useAuth();
  const [chats, setChats] = useState([]);

  useEffect(() => {
    if (!currentUser) return;
    
    const q = query(
      collection(db, 'chats'),
      where('userId', '==', currentUser.uid),
      orderBy('createdAt', 'desc')
    );
    
    const unsubscribe = onSnapshot(q, (querySnapshot) => {
      const chatsData = [];
      querySnapshot.forEach((doc) => {
        chatsData.push({ id: doc.id, ...doc.data() });
      });
      setChats(chatsData);
    });

    return () => unsubscribe();
  }, [currentUser]);

  return (
    <div>
      {chats.map((chat) => (
        <div key={chat.id} className="p-2 hover:bg-gray-100 rounded cursor-pointer">
          <div className="font-medium truncate">{chat.title || 'New Chat'}</div>
          <div className="text-sm text-gray-500 truncate">
            {chat.lastMessage || 'No messages yet'}
          </div>
        </div>
      ))}
    </div>
  );
}