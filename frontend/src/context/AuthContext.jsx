import { useCallback, useEffect, useState } from 'react';
import { apiRequest, API_BASE_URL } from '../lib/api';
import AuthContext from './authContextInstance';

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchCurrentUser = useCallback(async () => {
    const payload = await apiRequest('/auth/me', { method: 'GET' });
    return payload?.user || null;
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const user = await fetchCurrentUser();
      setCurrentUser(user);
      return user;
    } catch {
      setCurrentUser(null);
      return null;
    }
  }, [fetchCurrentUser]);

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
        const user = await fetchCurrentUser();
        if (!active) return;
        setCurrentUser(user);
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
  }, [fetchCurrentUser]);

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
