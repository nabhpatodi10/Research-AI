import { createContext, useContext, useEffect, useState } from 'react';
import { apiRequest, API_BASE_URL } from '../lib/api';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = async () => {
    try {
      const payload = await apiRequest('/auth/me', { method: 'GET' });
      setCurrentUser(payload?.user || null);
      return payload?.user || null;
    } catch {
      setCurrentUser(null);
      return null;
    }
  };

  const signup = async (name, email, password) => {
    const payload = await apiRequest('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ name, email, password }),
    });
    setCurrentUser(payload.user || null);
    return payload.user;
  };

  const login = async (email, password) => {
    const payload = await apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setCurrentUser(payload.user || null);
    return payload.user;
  };

  const googleLogin = () => {
    window.location.href = `${API_BASE_URL}/auth/google/start`;
  };

  const logout = async () => {
    await apiRequest('/auth/logout', { method: 'POST' });
    setCurrentUser(null);
  };

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const payload = await apiRequest('/auth/me', { method: 'GET' });
        if (!active) return;
        setCurrentUser(payload?.user || null);
      } catch {
        if (!active) return;
        setCurrentUser(null);
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, []);

  const value = {
    currentUser,
    loading,
    refreshUser,
    signup,
    login,
    googleLogin,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
