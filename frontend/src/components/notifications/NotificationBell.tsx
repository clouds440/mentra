import { Bell } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { notifications } from '../../services/notifications';

export function NotificationBell() {
  const { identity } = useAuth();
  const owner = identity?.learner_id;
  const [badge, setBadge] = useState<{ owner: string; count: number } | null>(null);
  useEffect(() => {
    if (!owner) return;
    const controller = new AbortController();
    let busy = false;
    async function refresh() {
      if (busy || document.hidden) return;
      busy = true;
      try {
        const page = await notifications.list(controller.signal, undefined, true, 1);
        if (!controller.signal.aborted) setBadge({ owner: owner!, count: page.unread_count });
      } catch { /* Keep the last confirmed count; the inbox exposes retry. */ }
      finally { busy = false; }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    window.addEventListener('mentra:notifications-changed', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener('mentra:notifications-changed', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [owner]);
  const count = badge?.owner === owner ? badge?.count ?? 0 : 0;
  return <Link to="/notifications" aria-label={`Notifications${count ? `, ${count} unread` : ''}`} className="ml-auto flex min-h-10 items-center gap-1 rounded-lg px-3 text-muted hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"><Bell aria-hidden="true" size={18} />{count > 0 && <span className="text-xs text-accent">{count > 99 ? '99+' : count}</span>}</Link>;
}
