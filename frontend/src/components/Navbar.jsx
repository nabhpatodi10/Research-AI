import { Link, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function Navbar() {
  const { currentUser, logout } = useAuth();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const location = useLocation();

  const sectionHref = (sectionId) => (location.pathname === '/' ? `#${sectionId}` : `/#${sectionId}`);

  return (
    <nav className="fixed top-0 inset-x-0 z-50 border-b border-blue-100/80 bg-white/85 backdrop-blur-xl">
      <div className="max-w-6xl mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-6">
            <Link to="/" className="brand-display text-2xl font-bold text-blue-900 tracking-tight">
              ResearchAI
            </Link>
            <div className="hidden md:flex items-center gap-1">
              <a href={sectionHref('home')} className="px-3 py-2 text-sm font-medium text-slate-700 hover:text-blue-900">
                Home
              </a>
              <a href={sectionHref('features')} className="px-3 py-2 text-sm font-medium text-slate-700 hover:text-blue-900">
                Features
              </a>
              <a href={sectionHref('benchmark')} className="px-3 py-2 text-sm font-medium text-slate-700 hover:text-blue-900">
                Benchmark
              </a>
              <a href={sectionHref('workflow')} className="px-3 py-2 text-sm font-medium text-slate-700 hover:text-blue-900">
                Workflow
              </a>
              <Link to="/feedback" className="px-3 py-2 text-sm font-medium text-slate-700 hover:text-blue-900">
                Feedback
              </Link>
            </div>
          </div>

          <div className="hidden md:flex items-center space-x-2">
            {currentUser ? (
              <>
                <Link to="/chat" className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:text-blue-900">
                  Chat
                </Link>
                <button
                  onClick={logout}
                  className="rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 transition"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:text-blue-900">
                  Log in
                </Link>
                <Link
                  to="/signup"
                  className="rounded-lg bg-blue-900 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 transition"
                >
                  Sign up
                </Link>
              </>
            )}
          </div>

          <div className="md:hidden flex items-center">
            <button
              onClick={() => setIsMenuOpen((open) => !open)}
              className="text-slate-700 hover:text-blue-900 focus:outline-none"
              aria-label="Toggle menu"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>

        {isMenuOpen && (
          <div className="md:hidden pb-4">
            <div className="rounded-xl border border-blue-100 bg-white p-3 shadow-sm">
              <div className="flex flex-col space-y-1">
                <a href={sectionHref('home')} className="rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>
                  Home
                </a>
                <a href={sectionHref('features')} className="rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>
                  Features
                </a>
                <a href={sectionHref('benchmark')} className="rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>
                  Benchmark
                </a>
                <a href={sectionHref('workflow')} className="rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>
                  Workflow
                </a>
                <Link to="/feedback" className="rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>
                  Feedback
                </Link>
                {currentUser ? (
                  <>
                    <Link to="/chat" className="rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>
                      Chat
                    </Link>
                    <button
                      onClick={() => {
                        setIsMenuOpen(false);
                        logout();
                      }}
                      className="mt-1 rounded-lg bg-blue-900 px-3 py-2 text-left text-sm font-semibold text-white hover:bg-blue-800"
                    >
                      Logout
                    </button>
                  </>
                ) : (
                  <>
                    <Link to="/login" className="rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-900" onClick={() => setIsMenuOpen(false)}>
                      Log in
                    </Link>
                    <Link to="/signup" className="rounded-lg bg-blue-900 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-800" onClick={() => setIsMenuOpen(false)}>
                      Sign up
                    </Link>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
