import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';

export default function PrivateRoute({ children }) {
  const { currentUser, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-4">
        <div className="rounded-xl border border-blue-100 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
          Checking your session...
        </div>
      </div>
    );
  }

  return currentUser ? children : <Navigate to="/login" replace />;
}
