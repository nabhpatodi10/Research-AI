import { useContext } from 'react';
import AuthContext from './authContextInstance';

export function useAuth() {
  return useContext(AuthContext);
}
