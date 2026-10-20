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
  return null;
}
