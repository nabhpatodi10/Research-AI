import { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import Home from './components/Home';
import Login from './components/Auth/Login';
import Signup from './components/Auth/Signup';
import Feedback from './components/Feedback';
import Navbar from './components/Navbar';
import Footer from './components/Footer';
import PrivacyPolicy from './components/PrivacyPolicy';

const ChatInterface = lazy(() => import('./components/Chat/ChatInterface'));

function App() {
  return (
    <Router>
      <AuthProvider>
        <div className="min-h-screen flex flex-col">
          <Navbar />
          <main className="flex-grow">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              <Route path="/privacy-policy" element={<PrivacyPolicy />} />
              <Route path="/feedback" element={<PrivateRoute><Feedback /></PrivateRoute>} />
              <Route
                path="/chat"
                element={
                  <PrivateRoute>
                    <Suspense
                      fallback={(
                        <div className="flex min-h-[60vh] items-center justify-center px-4">
                          <div className="rounded-xl border border-blue-100 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
                            Loading chat workspace...
                          </div>
                        </div>
                      )}
                    >
                      <ChatInterface />
                    </Suspense>
                  </PrivateRoute>
                }
              />
            </Routes>
          </main>
          <Footer className="mt-auto" />
        </div>
      </AuthProvider>
    </Router>
  );
}

export default App;
