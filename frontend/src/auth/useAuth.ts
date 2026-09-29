import { createContext, useContext } from 'react';

import type { User } from '../types/api';

export type Status = 'loading' | 'authenticated' | 'anonymous';

export interface AuthContextValue {
  status: Status;
  user: User | null;
  /** Shown on the sign-in page after sign-out or session expiry. */
  notice: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, fullName: string) => Promise<void>;
  startDemo: () => Promise<void>;
  signOut: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  return context;
}
