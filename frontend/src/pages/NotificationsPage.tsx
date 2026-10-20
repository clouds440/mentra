import { Bell, BellRing, Check, CalendarDays, ClipboardCheck, Settings2, ArrowUpRight } from 'lucide-react';
import { WorkspaceHeader, WorkspaceEmpty } from '../components/workspace/WorkspaceHeader';
import { usePageRefresh, refreshPage } from '../hooks/usePageRefresh';
import { Skeleton } from '../components/ui/Skeleton';
import { ApiError } from '../services/api';
import { Toggle } from '../components/ui/Toggle';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../components/auth/AuthProvider';
import { Button, buttonStyles } from '../components/ui/Button';
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
  const [activeAction, setActiveAction] = useState('');
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  async function load(before?: string) {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    setBusy(true); setError('');
    try {
      const result = await notifications.list(controller.signal, before, unread);
      if (!controller.signal.aborted) setPage(current => ({ ...result, items: before ? [...(current?.items ?? []), ...result.items].filter((item, index, all) => all.findIndex(other => other.id === item.id) === index) : result.items }));
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load notifications.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  usePageRefresh(() => { void load(); }, !busy, ['notifications']);
  useEffect(() => { setPage(null); void load(); return () => active.current?.abort(); }, [unread]); // eslint-disable-line react-hooks/exhaustive-deps
  async function edit(item: NotificationItem, action: 'read' | 'dismiss') {
    if (busy) return;
    const controller = new AbortController(); active.current?.abort(); active.current = controller;
    setBusy(true); setActiveAction(`${item.id}:${action}`); setError('');
    try {
      await notifications.edit(item, action, controller.signal);
      if (!controller.signal.aborted) { notificationChanged(); await load(); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to update notification. Reload and try again.'); }
    finally { setActiveAction(''); if (!controller.signal.aborted) setBusy(false); }
  }
  return <div className="h-full overflow-y-auto"><div className="page-container">
    <WorkspaceHeader title="Notifications" description="Your reminders and updates, together in one place." icon={Bell} actions={<Link className={buttonStyles({ variant: 'secondary', size: 'sm' })} to="/settings?tab=notifications"><Settings2 size={16} aria-hidden="true" />Preferences</Link>} />
    <div className="workspace-toolbar"><div className="flex items-center gap-3"><BellRing className="text-accent" size={18} aria-hidden="true" /><div><h2 className="font-medium text-heading">{unread ? 'Unread updates' : 'Your inbox'}</h2><p className="mt-1 text-xs text-muted">{page ? `${page.items.length} updates shown` : 'Checking for updates'}</p></div></div><div className="flex flex-wrap items-center gap-4"><Toggle label="Unread only" checked={unread} onChange={event => setUnread(event.target.checked)} /><Button variant="ghost" size="sm" disabled={busy} loading={busy && !activeAction} onClick={() => refreshPage(() => { void load(); })}>Refresh</Button></div></div>
    {error && <p role="alert" className="workspace-panel text-sm text-danger">{error} <button type="button" className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'ml-2 mt-1' })} onClick={() => refreshPage(() => { void load(); })}>Retry</button></p>}
    {!page && busy && <Skeleton variant="list" />}
    {page?.items.length === 0 && <WorkspaceEmpty icon={Bell} title={unread ? 'You’re all caught up' : 'A clear inbox'} description={unread ? 'No unread updates right now. Your next reminder will appear here.' : 'Reminders and updates will appear here when there’s something to share.'} />}
    <ul className="space-y-3">{page?.items.map(item => <li key={item.id} className={`workspace-item flex items-start gap-4 ${!item.read_at ? 'border-l-4 border-l-accent' : ''}`}>
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-control bg-active text-accent">{item.target_kind === 'event' ? <CalendarDays size={19} aria-hidden="true" /> : item.target_kind === 'assessment' ? <ClipboardCheck size={19} aria-hidden="true" /> : <Bell size={19} aria-hidden="true" />}</span>
      <div className="min-w-0 flex-1"><div className="flex flex-wrap items-start justify-between gap-2"><h2 className={`break-words text-sm ${item.read_at ? 'text-body' : 'font-medium text-heading'}`}>{item.title}</h2><span className="workspace-status">{item.read_at ? 'Read' : 'New'}</span></div><p className="mt-2 break-words text-sm leading-6 text-muted">{item.body}</p>
      <time className="mt-2 block text-xs text-subtle" dateTime={item.created_at}>{new Date(item.created_at).toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'})}</time>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        {item.target_kind !== 'none' && item.target_id && <Link className="mr-auto inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-accent hover:bg-hover focus-visible:ring-2 focus-visible:ring-accent" to={item.target_kind === 'event' ? `/progress?tab=events&event=${item.target_id}` : `/assessments?assessment=${item.target_id}`}>View {item.target_kind}<ArrowUpRight size={14} aria-hidden="true" /></Link>}
        {!item.read_at && <Button variant="ghost" size="sm" disabled={busy} loading={activeAction === `${item.id}:read`} onClick={() => void edit(item, 'read')}><Check size={14} aria-hidden="true" />Mark read</Button>}
        <Button variant="ghost" size="sm" disabled={busy} loading={activeAction === `${item.id}:dismiss`} onClick={() => void edit(item, 'dismiss')}>Dismiss</Button>
      </div></div>
    </li>)}</ul>
    {page?.next_cursor && <div className="flex justify-center"><Button variant="secondary" disabled={busy} loading={busy} onClick={() => void load(page.next_cursor!)}>Load more</Button></div>}
  </div></div>;
}
