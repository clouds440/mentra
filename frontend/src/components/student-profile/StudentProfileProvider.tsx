import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '../../services/api';
import { getProfile, profileError } from '../../services/studentProfile';
import type { StudentProfile } from '../../types/studentProfile';
import { useAuth } from '../auth/AuthProvider';
import { openBroadcastChannel } from '../../utils/broadcastChannel';

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
  const inFlight = useRef<Promise<StudentProfile> | null>(null);
  const refresh = useCallback(() => {
    if (inFlight.current) return inFlight.current;
    const controller = new AbortController();
    pending.current = controller;
    const requestGeneration = ++generation.current;
    const request: Promise<StudentProfile> = getProfile(controller.signal).then(next => {
      if (requestGeneration === generation.current && next.learner_id === authRef.current.identity?.learner_id) {
        setProfile(current => !current || next.version >= current.version ? next : current); setError(null);
      }
      return next;
    }).catch(failure => {
      if (!controller.signal.aborted && requestGeneration === generation.current) {
        if (failure instanceof ApiError && failure.status === 401) authRef.current.retry();
        else setError(profileError(failure));
      }
      throw failure;
    }).finally(() => {
      if (inFlight.current === request) inFlight.current = null;
      if (pending.current === controller) pending.current = null;
    });
    inFlight.current = request;
    return request;
  }, []);
  const replace = useCallback((next: StudentProfile) => {
    if (next.learner_id !== authRef.current.identity?.learner_id) return;
    ++generation.current;
    pending.current?.abort();
    inFlight.current = null;
    setProfile((current) => !current || next.version >= current.version ? next : current);
    setError(null);
    channel.current?.postMessage(next.learner_id);
  }, []);
  useEffect(() => {
    const restore = () => { void refresh().catch(() => {}); };
    restore();
    // BroadcastChannel may be blocked. Returning to a tab must still observe
    // saved settings; focus/visibility bursts share one canonical read.
    let lastForeground = 0;
    const foreground = () => {
      if (document.visibilityState !== 'visible' || Date.now() - lastForeground < 500) return;
      lastForeground = Date.now(); restore();
    };
    window.addEventListener('focus', foreground);
    document.addEventListener('visibilitychange', foreground);
    channel.current = openBroadcastChannel('mentra-profile');
    if (channel.current) {
      channel.current.onmessage = ({ data }) => { if (data === authRef.current.identity?.learner_id) restore(); };
    }
    return () => {
      ++generation.current;
      pending.current?.abort();
      inFlight.current = null;
      window.removeEventListener('focus', foreground);
      document.removeEventListener('visibilitychange', foreground);
      channel.current?.close();
      channel.current = null;
    };
  }, [refresh]);
  return <ProfileContext.Provider value={{ profile, error, refresh, replace }}>{children}</ProfileContext.Provider>;
}

export function useStudentProfile() {
  const value = useContext(ProfileContext);
  if (!value) throw new Error('useStudentProfile requires StudentProfileProvider');
  return value;
}
