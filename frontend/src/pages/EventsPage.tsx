import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../components/auth/AuthProvider';
import { Button, Input, Select } from '../components/ui';
import { EventEditor } from '../components/events/EventEditor';
import { events } from '../services/events';
import { notificationChanged } from '../services/notifications';
import type { EventPage, EventRecord, EventStatus } from '../types/events';

export function EventsPage() { const { identity } = useAuth(); return <Agenda key={identity?.learner_id} />; }
function Agenda() {
  const [params, setParams] = useSearchParams();
  const selected = params.get('event');
  const [page, setPage] = useState<EventPage | null>(null);
  const [detail, setDetail] = useState<EventRecord | null>(null);
  const [editing, setEditing] = useState<EventRecord | 'new' | null>(null);
  const [status, setStatus] = useState<EventStatus>('scheduled');
  const [query, setQuery] = useState('');
  const [range, setRange] = useState('upcoming');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const active = useRef<AbortController | null>(null);
  const mutation = useRef<AbortController | null>(null);
  const operation = useRef<{ key: string; id: string } | null>(null);
  async function load(cursor?: string) {
    active.current?.abort(); const controller = new AbortController(); active.current = controller; setError('');
    try {
      const after = new Date(); after.setDate(after.getDate() - (range === 'past' ? 180 : 1));
      const before = new Date(); before.setDate(before.getDate() + (range === 'past' ? 1 : 180));
      const filter = new URLSearchParams({ status, query, after: after.toISOString(), before: before.toISOString() });
      if (cursor) filter.set('cursor', cursor);
      // Cursor binds exact range values, so retain the first page's query.
      const filterKey = `${status}:${query}:${range}`;
      if (cursor && previousFilter.current?.key === filterKey) { filter.set('after', previousFilter.current.after); filter.set('before', previousFilter.current.before); }
      else previousFilter.current = { key: filterKey, after: filter.get('after')!, before: filter.get('before')! };
      const [result, current] = await Promise.all([events.list(filter, controller.signal), selected ? events.detail(selected, controller.signal) : Promise.resolve(null)]);
      if (!controller.signal.aborted) { setPage(old => ({ ...result, items: cursor ? [...(old?.items ?? []), ...result.items] : result.items })); setDetail(current); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load events.'); }
  }
  const previousFilter = useRef<{ key: string; after: string; before: string } | null>(null);
  useEffect(() => { setPage(null); setDetail(null); setDeleting(false); void load(); return () => active.current?.abort(); }, [selected, status, range]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => mutation.current?.abort(), []);
  async function change(item: EventRecord, action: EventStatus | 'delete') {
    if (busy) return;
    const key = `${item.id}:${item.revision}:${action}`;
    if (operation.current?.key !== key) operation.current = { key, id: crypto.randomUUID() };
    const controller = new AbortController(); mutation.current = controller; setBusy(true); setError('');
    try {
      if (action === 'delete') await events.remove(item, operation.current.id, controller.signal);
      else await events.status(item, action, operation.current.id, controller.signal);
      if (!controller.signal.aborted) { operation.current = null; notificationChanged(); setDeleting(false); if (action === 'delete') setParams({}); else await load(); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to update event. Refresh before retrying.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <div className="h-full overflow-y-auto"><div className="mx-auto max-w-4xl space-y-6 px-5 py-10">
    <div className="flex items-center justify-between"><h1 className="text-3xl font-medium">Events</h1><Button onClick={() => setEditing('new')}>New event</Button></div>
    <p className="text-sm text-muted">Keep track of quizzes, deadlines and study sessions. Each event has at most one reminder.</p>
    {error && <p role="alert" className="text-sm text-danger">{error} <button className="underline" onClick={() => void load()}>Refresh</button></p>}
    {editing && <EventEditor key={editing === 'new' ? 'new' : `${editing.id}:${editing.revision}`} current={editing === 'new' ? undefined : editing} onCancel={() => setEditing(null)} onSaved={item => { setEditing(null); setParams({ event: item.id }); void load(); }} />}
    {detail && <section className="space-y-3 rounded-xl border border-border p-5" aria-label="Event details">
      <div className="flex justify-between gap-3"><h2 className="text-xl font-medium">{detail.title}</h2><Button variant="ghost" size="sm" onClick={() => setParams({})}>Close</Button></div>
      <p className="text-sm text-muted">{detail.description}</p><p className="text-sm">{detail.local_date ?? new Date(detail.starts_at!).toLocaleString(undefined, { timeZone: detail.timezone })} · {detail.timezone}</p>
      <p className="text-sm text-muted">{detail.bucket} · Reminder {detail.reminder_state}{detail.reminder_due_at ? ` · ${new Date(detail.reminder_due_at).toLocaleString()}` : ''}</p>
      {detail.evidence?.map((source, index) => <div key={index} className="border-l border-border pl-3 text-sm"><p>{source.quote}</p>{source.source_deleted ? <p className="text-muted">Source conversation deleted</p> : source.conversation_id && <Link className="text-accent underline" to={`/chat/${source.conversation_id}`}>Source conversation</Link>}</div>)}
      <div className="flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={busy} onClick={() => setEditing(detail)}>Edit</Button>
      {(['scheduled', 'completed', 'cancelled'] as const).filter(value => value !== detail.status).map(value => <Button key={value} size="sm" variant="ghost" disabled={busy} onClick={() => void change(detail, value)}>{value === 'scheduled' ? 'Reopen' : value === 'completed' ? 'Complete' : 'Cancel event'}</Button>)}
      <Button variant="ghost" size="sm" disabled={busy} onClick={() => setDeleting(true)}>Delete</Button></div>
      {deleting && <div className="space-y-2"><p>Delete this event permanently?</p><Button disabled={busy} onClick={() => void change(detail, 'delete')}>Confirm delete</Button> <Button variant="ghost" disabled={busy} onClick={() => setDeleting(false)}>Keep event</Button></div>}
    </section>}
    <form className="flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); void load(); }}><Input aria-label="Search events" className="min-w-40 flex-1" value={query} maxLength={200} onChange={event => setQuery(event.target.value)} /><Button variant="secondary" type="submit">Search</Button><Select className="w-auto" aria-label="Event status" value={status} onChange={event => setStatus(event.target.value as EventStatus)}>{['scheduled', 'completed', 'cancelled'].map(value => <option key={value}>{value}</option>)}</Select><Select className="w-auto" aria-label="Event date range" value={range} onChange={event => setRange(event.target.value)}><option value="upcoming">Upcoming six months</option><option value="past">Past six months</option></Select></form>
    {!page && !error && <p role="status" className="text-muted">Loading events…</p>}
    {page?.items.length === 0 && <p className="py-8 text-muted">No events in this range.</p>}
    <ul className="divide-y divide-border">{page?.items.map(item => <li key={item.id}><button className="w-full rounded-lg py-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setParams({ event: item.id })}><span className="block font-medium">{item.title}</span><span className="text-sm text-muted">{item.local_date ?? new Date(item.starts_at!).toLocaleString(undefined, { timeZone: item.timezone })} · {item.timezone} · {item.bucket}</span></button></li>)}</ul>
    {page?.next_cursor && <Button variant="secondary" onClick={() => void load(page.next_cursor!)}>Load more</Button>}
  </div></div>;
}
