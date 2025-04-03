import { useState } from 'react';
import ChatHistory from './ChatHistory';
import MarkdownRenderer from './MarkdownRenderer';

export default function ChatInterface() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isNewChat, setIsNewChat] = useState(true);
  const [topic, setTopic] = useState('');
  const [outputFormat, setOutputFormat] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [researchContent, setResearchContent] = useState(null);

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
          sender: 'user',
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
        sender: 'ai'
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

  // Message component for better rendering
  const Message = ({ msg }) => {
    if (msg.isResearch) {
      return (
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
          <h3 className="font-bold mb-2">Research Results:</h3>
          <MarkdownRenderer content={msg.text} />
        </div>
      );
    }
    
    return (
      <div className={`max-w-3/4 p-3 rounded-lg ${
        msg.sender === 'user' ? 'bg-blue-900 text-white' :
        msg.sender === 'system' ? 'bg-gray-100 border border-gray-200' :
        msg.sender === 'system-error' ? 'bg-red-100 border border-red-200 text-red-700' :
        'bg-white border border-gray-200'
      }`}>
        {msg.sender.startsWith('ai') ? (
          <MarkdownRenderer content={msg.text} />
        ) : (
          msg.text
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
              className="w-full p-2 border border-gray-300 rounded"
            />
          </div>
          <div className="space-y-2">
            <button 
              onClick={handleNewChat}
              className="w-full text-left p-2 hover:bg-gray-100 rounded"
            >
              New Chat
            </button>
            <ChatHistory />
          </div>
        </div>
      </div>
      
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col pt-16">
        {/* Chat Header */}
        <div className="p-4 border-b border-gray-200 bg-white">
          <h2 className="text-lg font-semibold">Research Assistant</h2>
        </div>
        
        {/* Messages */}
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
                        className="w-full p-3 border border-gray-300 rounded"
                        disabled={loading}
                        required
                      />
                    </div>
                    <div>
                      <input
                        type="text"
                        value={outputFormat}
                        onChange={(e) => setOutputFormat(e.target.value)}
                        placeholder="Output Format (e.g., Report, Summary)"
                        className="w-full p-3 border border-gray-300 rounded"
                        disabled={loading}
                        required
                      />
                    </div>
                    <button
                      type="submit"
                      className="w-full px-4 py-2 bg-blue-900 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                      disabled={!topic || !outputFormat || loading}
                    >
                      {loading ? 'Starting Research...' : 'Start Research'}
                    </button>
                  </form>
                </div>
              ) : (
                <div className="text-center">
                  <h3 className="text-xl font-medium">Hello! I'm your research assistant.</h3>
                  <p className="text-gray-600">How can I help with your academic inquiries today?</p>
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
        
        {/* Input Area */}
        {!isNewChat && (
          <div className="sticky bottom-0 p-4 border-t border-gray-200 bg-white">
            <form onSubmit={handleSend} className="flex">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a research question..."
                className="flex-1 p-3 border border-gray-300 rounded-l focus:outline-none focus:ring-1 focus:ring-blue-500"
                disabled={loading || !sessionId}
              />
              <button
                type="submit"
                className="px-4 bg-blue-900 text-white rounded-r hover:bg-blue-700 disabled:opacity-50"
                disabled={loading || !input.trim() || !sessionId}
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