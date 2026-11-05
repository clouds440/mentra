import { Bell } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { notifications, watchNotifications } from '../../services/notifications';

export function NotificationBell({ quiet = false }: { quiet?: boolean }) {
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
        const page = await notifications.unread(controller.signal);
        if (!controller.signal.aborted) setBadge({ owner: owner!, count: page.unread_count });
      } catch { /* Keep the last confirmed count; the inbox exposes retry. */ }
      finally { busy = false; }
    }
    void refresh();
    const stop = watchNotifications(owner, value => {
      if (!controller.signal.aborted) setBadge({ owner, count: value.unread_count });
    });
    window.addEventListener('mentra:notifications-changed', refresh);
    return () => { stop(); controller.abort(); window.removeEventListener('mentra:notifications-changed', refresh); };
  }, [owner]);
  const count = badge?.owner === owner ? badge?.count ?? 0 : 0;
  return <Link to="/notifications" aria-label={`Notifications${count ? `, ${count} unread` : ''}`} className={`${quiet ? 'quiet-notification ' : ''}workspace-chrome-control icon-control ml-auto flex min-h-8 items-center justify-center gap-1 rounded-control px-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent`}><Bell aria-hidden="true" size={18} />{count > 0 && <span aria-hidden="true" className="notification-count text-xs text-accent">{count > 99 ? '99+' : count}</span>}</Link>;
}
