import { Link, useLocation } from 'react-router-dom';

export default function Footer() {
  const location = useLocation();
  const year = new Date().getFullYear();
  const sectionHref = (sectionId) => (location.pathname === '/' ? `#${sectionId}` : `/#${sectionId}`);

  return (
    <footer className="bg-slate-950 text-white pt-14 pb-10">
      <div className="max-w-6xl mx-auto px-4">
        <div className="grid gap-10 md:grid-cols-[1.2fr_0.9fr_0.9fr]">
          <div>
            <h3 className="brand-display text-2xl font-bold text-blue-300">ResearchAI</h3>
            <p className="mt-3 max-w-md text-sm leading-6 text-slate-300">
              A research-first workspace for discovering sources, synthesizing context, and producing structured outputs with AI assistance.
            </p>
          </div>

          <div>
            <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-blue-200">Explore</h4>
            <ul className="mt-4 space-y-2 text-sm">
              <li><a href={sectionHref('home')} className="text-slate-300 hover:text-white">Home</a></li>
              <li><a href={sectionHref('features')} className="text-slate-300 hover:text-white">Features</a></li>
              <li><a href={sectionHref('benchmark')} className="text-slate-300 hover:text-white">Benchmark</a></li>
              <li><a href={sectionHref('workflow')} className="text-slate-300 hover:text-white">Workflow</a></li>
              <li><Link to="/feedback" className="text-slate-300 hover:text-white">Feedback</Link></li>
              <li><Link to="/privacy-policy" className="text-slate-300 hover:text-white">Privacy Policy</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-blue-200">Account</h4>
            <ul className="mt-4 space-y-2 text-sm">
              <li><Link to="/login" className="text-slate-300 hover:text-white">Log in</Link></li>
              <li><Link to="/signup" className="text-slate-300 hover:text-white">Sign up</Link></li>
              <li><Link to="/chat" className="text-slate-300 hover:text-white">Open chat</Link></li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-slate-800 pt-6 text-xs text-slate-400">
          <p>© {year} ResearchAI. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
