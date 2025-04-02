import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Navbar() {
  const { currentUser, logout } = useAuth();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg">
      <div className="max-w-6xl mx-auto px-4">
        <div className="flex justify-between items-center py-4">
          <div className="flex items-center space-x-4">
            <Link to="/" className="text-2xl font-bold text-blue-900">ResearchAI</Link>
            <div className="hidden md:flex space-x-6">
              <Link to="/" className="text-gray-700 hover:text-blue-900">Home</Link>
              <Link to="/" className="text-gray-700 hover:text-blue-900">About</Link>
              <Link to="/" className="text-gray-700 hover:text-blue-900">Features</Link>
            </div>
          </div>
          <div className="flex items-center space-x-4">
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
        </div>
      </div>
    </nav>
  );
}