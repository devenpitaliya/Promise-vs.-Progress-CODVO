import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { authApi } from '../api/endpoints';
import { SESSION_EXPIRED_EVENT, tokenStore } from '../lib/api';
import { AuthContext, type AuthContextValue, type Status } from './useAuth';
import type { TokenResponse, User } from '../types/api';

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>(() => (tokenStore.get() ? 'loading' : 'anonymous'));
  const [user, setUser] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const endSession = useCallback(
    (message: string | null) => {
      tokenStore.clear();
      queryClient.clear();
      setUser(null);
      setNotice(message);
      setStatus('anonymous');
    },
    [queryClient],
  );

  useEffect(() => {
    if (!tokenStore.get()) return;
    let cancelled = false;
    authApi
      .me()
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        setStatus('authenticated');
      })
      .catch(() => !cancelled && endSession('Your session has expired. Please sign in again.'));
    return () => {
      cancelled = true;
    };
  }, [endSession]);

  useEffect(() => {
    const onExpired = () => endSession('Your session has expired. Please sign in again.');
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [endSession]);

  const accept = useCallback((response: TokenResponse) => {
    tokenStore.set(response.access_token);
    setUser(response.user);
    setNotice(null);
    setStatus('authenticated');
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      notice,
      signIn: async (email, password) => accept(await authApi.login(email, password)),
      signUp: async (email, password, fullName) => accept(await authApi.register(email, password, fullName)),
      startDemo: async () => accept(await authApi.demo()),
      signOut: () => endSession('You have been signed out.'),
    }),
    [status, user, notice, accept, endSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
