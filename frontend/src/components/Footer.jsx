import { Link } from 'react-router-dom';

export default function Footer() {
    return (
      <footer className="bg-gray-900 text-white py-12">
        <div className="max-w-6xl mx-auto px-4">
          <div className="grid md:grid-cols-3 gap-8">
            <div>
              <h3 className="text-xl font-bold mb-4">ResearchAI</h3>
              <p className="text-gray-400">
                AI-powered research tools to accelerate your academic insights
              </p>
            </div>

            <div>
            <h4 className="font-semibold mb-4">Platform</h4>
            <ul className="space-y-2">
                <li><Link to="/features" className="text-gray-400 hover:text-white">Features</Link></li>
                <li><Link to="/how-it-works" className="text-gray-400 hover:text-white">How it works</Link></li>
                <li><Link to="/feedback" className="text-gray-400 hover:text-white">Feedback</Link></li>
            </ul>
            </div>
            
            <div>
              <h4 className="font-semibold mb-4">Account</h4>
              <ul className="space-y-2">
                <li><a href="/login" className="text-gray-400 hover:text-white">Log in</a></li>
                <li><a href="/signup" className="text-gray-400 hover:text-white">Sign up</a></li>
              </ul>
            </div>
          </div>
          
          <div className="border-t border-gray-800 mt-8 pt-8 text-center text-gray-400">
            <p>© 2025 ResearchAI. All rights reserved.</p>
          </div>
        </div>
      </footer>
    );
  }