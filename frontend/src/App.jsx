import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import Home from './components/Home';
import Login from './components/Auth/Login';
import Signup from './components/Auth/Signup';
import ChatInterface from './components/Chat/ChatInterface';
import Feedback from './components/Feedback';
import Navbar from './components/Navbar';
import Footer from './components/Footer';

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
              <Route path="/feedback" element={<PrivateRoute><Feedback /></PrivateRoute>} />
              <Route path="/chat" element={<PrivateRoute><ChatInterface /></PrivateRoute>} />
            </Routes>
          </main>
          <Footer className="mt-auto" />
        </div>
      </AuthProvider>
    </Router>
  );
}

export default App;