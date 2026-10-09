import { Toggle } from '../components/ui/Toggle';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../components/auth/AuthProvider';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { notifications, notificationChanged } from '../services/notifications';
import type { NotificationItem, NotificationPage } from '../types/notifications';

export function NotificationsPage() {
  const { identity } = useAuth();
  return <Inbox key={identity?.learner_id} />;
}
function Inbox() {
  const [page, setPage] = useState<NotificationPage | null>(null);
  const [unread, setUnread] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  async function load(before?: string) {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    setBusy(true); setError('');
    try {
      const result = await notifications.list(controller.signal, before, unread);
      if (!controller.signal.aborted) setPage(current => ({ ...result, items: before ? [...(current?.items ?? []), ...result.items].filter((item, index, all) => all.findIndex(other => other.id === item.id) === index) : result.items }));
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load notifications.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  useEffect(() => { setPage(null); void load(); return () => active.current?.abort(); }, [unread]); // eslint-disable-line react-hooks/exhaustive-deps
  async function edit(item: NotificationItem, action: 'read' | 'dismiss') {
    if (busy) return;
    const controller = new AbortController(); active.current?.abort(); active.current = controller;
    setBusy(true); setError('');
    try {
      await notifications.edit(item, action, controller.signal);
      if (!controller.signal.aborted) { notificationChanged(); await load(); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to update notification. Reload and try again.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <div className="h-full overflow-y-auto"><div className="page-container">
    <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="page-title">Notifications</h1><Link className="text-sm text-accent underline" to="/settings?tab=notifications">Notification settings</Link></div>
    <div className="flex items-center justify-between"><Toggle label="Unread only" checked={unread} onChange={event => setUnread(event.target.checked)} /><Button variant="ghost" size="sm" disabled={busy} onClick={() => void load()}>Refresh</Button></div>
    {error && <p role="alert" className="text-sm text-danger">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>}
    {!page && busy && <div role="status" className="flex gap-2 text-muted"><Spinner />Loading notifications…</div>}
    {page?.items.length === 0 && <p className="py-10 text-muted">{unread ? 'No unread notifications.' : 'Your notifications will appear here.'}</p>}
    <ul className="divide-y divide-border">{page?.items.map(item => <li key={item.id} className="space-y-2 py-5">
      <h2 className={item.read_at ? 'text-muted' : 'font-medium text-heading'}>{item.title}</h2><p className="text-sm text-muted">{item.body}</p>
      <time className="block text-xs text-subtle" dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
      <div className="flex flex-wrap items-center gap-3">
        {item.target_kind !== 'none' && item.target_id && <Link className="text-sm text-accent underline" to={item.target_kind === 'event' ? `/progress?tab=events&event=${item.target_id}` : `/assessments?assessment=${item.target_id}`}>View {item.target_kind}</Link>}
        {!item.read_at && <Button variant="ghost" size="sm" disabled={busy} onClick={() => void edit(item, 'read')}>Mark read</Button>}
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => void edit(item, 'dismiss')}>Dismiss</Button>
      </div>
    </li>)}</ul>
    {page?.next_cursor && <Button variant="secondary" disabled={busy} onClick={() => void load(page.next_cursor!)}>Load more</Button>}
  </div></div>;
}
