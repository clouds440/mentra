import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '../../services/api';
import { getProfile, profileError } from '../../services/studentProfile';
import type { StudentProfile } from '../../types/studentProfile';
import { useAuth } from '../auth/AuthProvider';

interface ProfileContextValue {
  profile: StudentProfile | null;
  error: string | null;
  refresh: () => Promise<StudentProfile>;
  replace: (profile: StudentProfile) => void;
}
const ProfileContext = createContext<ProfileContextValue | null>(null);

export function StudentProfileProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const authRef = useRef(auth);
  authRef.current = auth;
  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);
  const refresh = useCallback(async () => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const requestGeneration = ++generation.current;
    try {
      const next = await getProfile(controller.signal);
      if (requestGeneration === generation.current) { setProfile(next); setError(null); }
      return next;
    } catch (failure) {
      if (!controller.signal.aborted && requestGeneration === generation.current) {
        if (failure instanceof ApiError && failure.status === 401) authRef.current.retry();
        else setError(profileError(failure));
      }
      throw failure;
    }
  }, []);
  const replace = useCallback((next: StudentProfile) => {
    ++generation.current;
    pending.current?.abort();
    setProfile((current) => !current || next.version >= current.version ? next : current);
    setError(null);
    channel.current?.postMessage(next.learner_id);
  }, []);
  useEffect(() => {
    const restore = () => { void refresh().catch(() => {}); };
    restore();
    window.addEventListener('focus', restore);
    if (typeof BroadcastChannel !== 'undefined') {
      channel.current = new BroadcastChannel('mentra-profile');
      channel.current.onmessage = ({ data }) => { if (data === authRef.current.identity?.learner_id) restore(); };
    }
    return () => {
      ++generation.current;
      pending.current?.abort();
      channel.current?.close();
      channel.current = null;
      window.removeEventListener('focus', restore);
    };
  }, [refresh]);
  return <ProfileContext.Provider value={{ profile, error, refresh, replace }}>{children}</ProfileContext.Provider>;
}

export function useStudentProfile() {
  const value = useContext(ProfileContext);
  if (!value) throw new Error('useStudentProfile requires StudentProfileProvider');
  return value;
}
