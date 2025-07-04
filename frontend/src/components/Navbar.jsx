import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function Navbar() {
  const { currentUser, logout } = useAuth();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <nav className="fixed top-0 inset-x-0 z-50 bg-white shadow">
      <div className="max-w-6xl mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center mr-6">
            <Link to="/" className="text-2xl font-bold text-blue-900 mr-8">ResearchAI</Link>
            <div className="hidden md:flex space-x-6">
              <Link to="/" className="text-gray-700 hover:text-blue-900">Home</Link>
              <Link to="/" className="text-gray-700 hover:text-blue-900">About</Link>
              <Link to="/" className="text-gray-700 hover:text-blue-900">Features</Link>
            </div>
          </div>

          <div className="hidden md:flex items-center space-x-4">
            {currentUser ? (
              <>
                <Link to="/chat" className="text-gray-700 hover:text-blue-900">Chat</Link>
                <button
                  onClick={logout}
                  className="px-4 py-2 text-gray-700 hover:text-blue-900"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="text-gray-700 hover:text-blue-900">Log in</Link>
                <Link
                  to="/signup"
                  className="px-4 py-2 bg-blue-900 text-white rounded hover:bg-blue-700"
                >
                  Sign up
                </Link>
              </>
            )}
          </div>

          <div className="md:hidden flex items-center">
            <button onClick={() => setIsMenuOpen(!isMenuOpen)} className="text-gray-700 hover:text-blue-900 focus:outline-none">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>

        {isMenuOpen && (
          <div className="md:hidden pb-4">
            <div className="flex flex-col space-y-2">
              <Link to="/" className="text-gray-700 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>Home</Link>
              <Link to="/" className="text-gray-700 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>About</Link>
              <Link to="/" className="text-gray-700 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>Features</Link>
              {currentUser ? (
                <>
                  <Link to="/chat" className="text-gray-700 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>Chat</Link>
                  <button onClick={() => { setIsMenuOpen(false); logout(); }} className="text-left text-gray-700 hover:text-blue-900">Logout</button>
                </>
              ) : (
                <>
                  <Link to="/login" className="text-gray-700 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>Log in</Link>
                  <Link to="/signup" className="text-gray-700 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>Sign up</Link>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}