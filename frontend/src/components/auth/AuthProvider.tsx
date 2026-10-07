import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import * as authApi from '../../services/auth';
import { ApiError } from '../../services/api';
import type { AuthCredentials, AuthIdentity } from '../../types/auth';

type AuthState =
  | { status: 'loading' | 'anonymous'; identity: null; error: null }
  | { status: 'authenticated'; identity: AuthIdentity; error: null }
  | { status: 'error'; identity: null; error: string };

interface AuthContextValue {
  status: AuthState['status'];
  identity: AuthIdentity | null;
  error: string | null;
  login: (credentials: AuthCredentials) => Promise<void>;
  register: (credentials: AuthCredentials) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', identity: null, error: null });
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const channel = useRef<BroadcastChannel | null>(null);

  const restore = useCallback(async (initial = false) => {
    if (busy.current) return;
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const requestGeneration = ++generation.current;
    if (initial) setState({ status: 'loading', identity: null, error: null });
    try {
      const identity = await authApi.getSession(controller.signal);
      if (requestGeneration === generation.current) {
        setState({ status: 'authenticated', identity, error: null });
      }
    } catch (error) {
      if (controller.signal.aborted || requestGeneration !== generation.current) return;
      if (error instanceof ApiError && error.status === 401) {
        setState({ status: 'anonymous', identity: null, error: null });
      } else {
        setState((current) => current.status === 'loading' || current.status === 'error'
          ? { status: 'error', identity: null, error: authApi.authErrorMessage(error) }
          : current);
      }
    }
  }, []);

  useEffect(() => {
    void restore(true);
    const refresh = () => { if (document.visibilityState === 'visible') void restore(); };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    if (typeof BroadcastChannel !== 'undefined') {
      channel.current = new BroadcastChannel('mentra-auth');
      channel.current.onmessage = () => { void restore(); };
    }
    return () => {
      ++generation.current;
      pending.current?.abort();
      channel.current?.close();
      channel.current = null;
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [restore]);

  async function authenticate(kind: 'login' | 'register', credentials: AuthCredentials) {
    if (busy.current) return;
    busy.current = true;
    pending.current?.abort();
    ++generation.current;
    try {
      const identity = await authApi[kind](credentials);
      setState({ status: 'authenticated', identity, error: null });
      channel.current?.postMessage('changed');
    } finally {
      busy.current = false;
    }
  }

  async function logout() {
    if (busy.current) return;
    busy.current = true;
    pending.current?.abort();
    ++generation.current;
    try {
      await authApi.logout();
      setState({ status: 'anonymous', identity: null, error: null });
      channel.current?.postMessage('changed');
    } finally {
      busy.current = false;
    }
  }

  return (
    <AuthContext.Provider value={{ ...state, login: (credentials) => authenticate('login', credentials),
      register: (credentials) => authenticate('register', credentials), logout, retry: () => { void restore(true); } }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth requires AuthProvider');
  return value;
}
