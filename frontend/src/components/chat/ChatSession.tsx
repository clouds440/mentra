import { useEffect } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { chatStore } from '../../stores/chatStore';

export function ChatSession() {
  const { identity, status } = useAuth();
  const owner = identity?.learner_id;
  useEffect(() => {
    if (status === 'authenticated' && owner) void chatStore.start(owner);
    else if (status === 'anonymous') chatStore.stop(true);
  }, [owner, status]);
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') void chatStore.sync(); };
    window.addEventListener('focus', refresh); window.addEventListener('online', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.removeEventListener('focus', refresh); window.removeEventListener('online', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, []);
  return null;
}
