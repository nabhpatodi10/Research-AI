import { useState, useEffect } from 'react';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { db } from '../../firebase';
import { useAuth } from '../../context/AuthContext';
import ChatHistory from './ChatHistory';
import MarkdownRenderer from './MarkdownRenderer';

// Helper function to parse Python-style strings to JSON
const parseContentString = (contentStr) => {
  try {
    // Handle invalid inputs
    if (!contentStr || typeof contentStr !== 'string') {
      console.error("Invalid content string:", contentStr);
      return ['Invalid Content', 'Could not parse message'];
    }

    // Escape function to properly format text for markdown rendering
    const formatTextForMarkdown = (text) => {
      if (typeof text !== 'string') return text;
      
      // Ensure literal \n sequences are converted to actual newlines first
      const withProperNewlines = text.replace(/\\n/g, '\n');
      
      // Then convert single newlines to markdown line breaks (adding two spaces before each newline)
      return withProperNewlines.replace(/\n/g, '  \n');
    };

    // Check if this is a Python list format: ['type', 'content']
    if (contentStr.startsWith('[') && contentStr.endsWith(']')) {
      // Extract the content between the outer brackets
      const innerContent = contentStr.slice(1, -1);
      
      // Find the first comma that's not inside nested quotes or brackets
      let inQuote = false;
      let quoteChar = null;
      let bracketDepth = 0;
      let commaIndex = -1;
      
      for (let i = 0; i < innerContent.length; i++) {
        const char = innerContent[i];
        
        // Handle quotes (respecting escape sequences)
        if ((char === "'" || char === '"') && (i === 0 || innerContent[i-1] !== '\\')) {
          if (!inQuote) {
            inQuote = true;
            quoteChar = char;
          } else if (char === quoteChar) {
            inQuote = false;
          }
        } 
        // Only track brackets if not inside a quoted string
        else if (!inQuote) {
          if (char === '[') bracketDepth++;
          else if (char === ']') bracketDepth--;
          // Find the comma that separates the first and second elements
          else if (char === ',' && bracketDepth === 0) {
            commaIndex = i;
            break;
          }
        }
      }
      
      if (commaIndex !== -1) {
        // Extract the message type (first element)
        let messageType = innerContent.substring(0, commaIndex).trim();
        // Remove surrounding quotes if present
        messageType = messageType.replace(/^['"](.*)['"]$/, '$1');
        
        // Extract the message content (second element)
        let messageContent = innerContent.substring(commaIndex + 1).trim();
        
        // If message content starts and ends with quotes, it's a string
        if ((messageContent.startsWith("'") && messageContent.endsWith("'")) || 
            (messageContent.startsWith('"') && messageContent.endsWith('"'))) {
          // Extract the string content (remove surrounding quotes)
          messageContent = messageContent.slice(1, -1);
          
          // Format the string content for markdown rendering
          messageContent = formatTextForMarkdown(messageContent);
        } 
        // Otherwise try to parse it as JSON (for objects, etc.)
        else {
          try {
            messageContent = JSON.parse(
              messageContent
                .replace(/'/g, '"')
                .replace(/None/g, 'null')
                .replace(/True/g, 'true')
                .replace(/False/g, 'false')
            );
          } catch (e) {
            // Keep as string if JSON parsing fails
            // Also format it for markdown if it's a string
            messageContent = formatTextForMarkdown(messageContent);
          }
        }
        
        return [messageType, messageContent];
      }
    }
    
    // Fallback to original algorithm
    const jsonString = contentStr
      .replace(/'/g, '"')
      .replace(/None/g, 'null')
      .replace(/True/g, 'true')
      .replace(/False/g, 'false');

    let parsed = JSON.parse(jsonString);
    
    // Also format any string content in the parsed result
    if (Array.isArray(parsed) && parsed.length === 2 && typeof parsed[1] === 'string') {
      parsed[1] = formatTextForMarkdown(parsed[1]);
    }
    
    return parsed;
  } catch (error) {
    console.error("Error parsing content:", error, contentStr);
    return ['Invalid Content', 'Could not parse message'];
  }
};

export default function ChatInterface() {
  const { currentUser } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isNewChat, setIsNewChat] = useState(true);
  const [topic, setTopic] = useState('');
  const [outputFormat, setOutputFormat] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [researchContent, setResearchContent] = useState(null);

  useEffect(() => {
    const saveChatSession = async () => {
      if (!currentUser || !sessionId || !topic) return;
      
      const userChatsRef = doc(db, 'user_chats', currentUser.uid);
      await setDoc(userChatsRef, {
        sessions: {
          [sessionId]: {
            topic,
            createdAt: new Date()
          }
        }
      }, { merge: true });
    };

    saveChatSession();
  }, [sessionId, currentUser, topic]);

  const handleNewChat = () => {
    setIsNewChat(true);
    setTopic('');
    setOutputFormat('');
    setMessages([]);
    setSessionId(null);
    setResearchContent(null);
  };

  const handleInitialSubmit = async (e) => {
    e.preventDefault();
    if (!topic.trim() || !outputFormat.trim()) return;

    setLoading(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/research', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          topic,
          output_format: outputFormat
        }),
      });

      if (!response.ok) throw new Error('Research initialization failed');
      
      const data = await response.json();
      setSessionId(data.session_id);
      setResearchContent(data.final_content);

      setMessages(prev => [
        ...prev,
        {
          text: `Research session started\nTopic: ${topic}\nOutput Format: ${outputFormat}`,
          sender: 'user'
        },
        {
          text: data.final_content,
          sender: 'ai',
          isResearch: true
        }
      ]);
      
      setIsNewChat(false);
    } catch (err) {
      console.error('Error starting research:', err);
      setMessages(prev => [...prev, { 
        text: "Failed to initialize research session. Please try again.", 
        sender: 'system-error' 
      }]);
    }
    setLoading(false);
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || !sessionId) return;
    
    setLoading(true);
    const userMessage = { text: input, sender: 'user' };
    setMessages(prev => [...prev, userMessage]);
    
    try {
      const response = await fetch('http://127.0.0.1:8000/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          user_input: input,
          session_id: sessionId
        }),
      });

      if (!response.ok) throw new Error('Chat request failed');
      
      const data = await response.json();
      
      setMessages(prev => [...prev, { 
        text: data.response, 
        sender: 'ai',
        isChat: true
      }]);
    } catch (err) {
      console.error('Error sending message:', err);
      setMessages(prev => [...prev, { 
        text: "Sorry, I couldn't process your request.", 
        sender: 'ai-error' 
      }]);
    }
    
    setInput('');
    setLoading(false);
  };

  const loadChat = async (sessionId) => {
    try {
      setLoading(true);
      setMessages([]);
      
      // 1. Get session metadata
      const userChatsRef = doc(db, 'user_chats', currentUser.uid);
      const userChatsSnap = await getDoc(userChatsRef);
      
      if (!userChatsSnap.exists()) throw new Error('No chat sessions found');

      const sessions = userChatsSnap.data().sessions || {};
      const sessionData = sessions[sessionId] || { topic: 'Untitled Session' };

      // 2. Get messages array from Firestore
      const sessionRef = doc(db, 'chats', sessionId);
      const sessionSnap = await getDoc(sessionRef);
      if (!sessionSnap.exists()) throw new Error('Chat session not found');

      const messagesData = sessionSnap.data().messages || [];
      
      // 3. Process messages with content filtering
      const processedMessages = messagesData
        .map((msgStr, index) => {
          try {
            const msg = JSON.parse(msgStr);
            const content = typeof msg.content === 'string' 
              ? parseContentString(msg.content) 
              : msg.content;
            const messageType = content[0];
            const messageContent = content[1];

            // Handle human messages
            if (msg.type === 'human') {
              return {
                id: `msg-${index}`,
                text: typeof messageContent === 'object' && messageContent !== null
                  ? `Topic: ${messageContent.topic}\nOutput Format: ${messageContent.output_format}`
                  : messageContent,
                sender: 'user',
                raw: msg
              };
            }

            // Handle AI messages
            if (msg.type === 'ai' && (messageType === 'Final Document' || messageType === 'Chat')) {
              return {
                id: `msg-${index}`,
                text: messageContent,
                sender: 'ai',
                isResearch: messageType === 'Final Document',
                raw: msg
              };
            }

            return null;
          } catch (error) {
            console.error("Error processing message:", error);
            return null;
          }
        })
        .filter(msg => msg !== null);

      setSessionId(sessionId);
      setTopic(sessionData.topic);
      setMessages([
        ...processedMessages
      ]);
      setIsNewChat(false);
    } catch (error) {
      console.error("Error loading chat:", error);
      setMessages([{
        text: "Failed to load chat history. Please try again.",
        sender: 'system-error'
      }]);
    } finally {
      setLoading(false);
    }
  };

  // Message component remains the same
  const Message = ({ msg }) => {
    if (msg.isResearch) {
      return (
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
          <h3 className="font-bold mb-2">Research Document:</h3>
          <MarkdownRenderer content={msg.text} />
        </div>
      );
    }
    
    return (
      <div className={`max-w-3/4 p-3 rounded-lg ${
        msg.sender === 'user' ? 'bg-blue-900 text-white' :
        msg.sender === 'ai' ? 'bg-white border border-gray-200' :
        msg.sender === 'system-error' ? 'bg-red-100 border border-red-200 text-red-700' :
        'bg-gray-100 border border-gray-200'
      }`}>
        {msg.sender === 'ai' ? (
          <MarkdownRenderer content={msg.text} />
        ) : (
          <div className="whitespace-pre-wrap">{msg.text}</div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <div className="w-64 bg-white border-r border-gray-200 pt-16">
        <div className="p-4 border-b border-gray-200">
          <h1 className="text-xl font-bold">ResearchAI</h1>
        </div>
        <div className="p-4">
          <div className="mb-4">
            <input
              type="text"
              placeholder="Search chats..."
              className="w-full p-2 border border-gray-300 rounded text-sm"
            />
          </div>
          <div className="space-y-2">
            <button 
              onClick={handleNewChat}
              className="w-full text-left p-2 hover:bg-gray-100 rounded text-sm font-medium"
            >
              + New Chat
            </button>
            <ChatHistory onChatSelect={loadChat} />
          </div>
        </div>
      </div>
      
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col pt-16">
        <div className="p-4 border-b border-gray-200 bg-white">
          <h2 className="text-lg font-semibold">
            {sessionId ? `Research: ${topic}` : 'New Research Session'}
          </h2>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 space-y-4 pb-24">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              {isNewChat ? (
                <div className="text-center max-w-md w-full space-y-4">
                  <h3 className="text-xl font-medium">Start New Research</h3>
                  <form onSubmit={handleInitialSubmit} className="space-y-4">
                    <div>
                      <input
                        type="text"
                        value={topic}
                        onChange={(e) => setTopic(e.target.value)}
                        placeholder="Research Topic"
                        className="w-full p-3 border border-gray-300 rounded text-sm"
                        required
                      />
                    </div>
                    <div>
                      <input
                        type="text"
                        value={outputFormat}
                        onChange={(e) => setOutputFormat(e.target.value)}
                        placeholder="Output Format (e.g., Report, Summary)"
                        className="w-full p-3 border border-gray-300 rounded text-sm"
                        required
                      />
                    </div>
                    <button
                      type="submit"
                      className="w-full px-4 py-2 bg-blue-900 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm"
                      disabled={!topic || !outputFormat || loading}
                    >
                      {loading ? 'Initializing...' : 'Start Research'}
                    </button>
                  </form>
                </div>
              ) : (
                <div className="text-center">
                  <h3 className="text-xl font-medium">Ready for Research</h3>
                  <p className="text-gray-600 text-sm">Start asking questions about your topic</p>
                </div>
              )}
            </div>
          ) : (
            messages.map((msg, index) => (
              <div 
                key={index} 
                className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <Message msg={msg} />
              </div>
            ))
          )}
        </div>
        
        {!isNewChat && (
          <div className="sticky bottom-0 p-4 border-t border-gray-200 bg-white">
            <form onSubmit={handleSend} className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a research question..."
                className="flex-1 p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                disabled={loading}
              />
              <button
                type="submit"
                className="px-4 py-2 bg-blue-900 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
                disabled={loading || !input.trim()}
              >
                {loading ? 'Sending...' : 'Send'}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}