import { useEffect, useRef, useState } from 'react';
import { Button, Input, Select } from '../ui';
import { events } from '../../services/events';
import type { EventDraft, EventKind, EventRecord, TemporalPreview } from '../../types/events';

function localTime(instant: string | null, zone: string) {
  if (!instant) return '';
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(instant));
  const get = (key: string) => parts.find(part => part.type === key)?.value;
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}
export function EventEditor({ current, initial, onConfirmed, onSaved, onCancel }: { current?: EventRecord; initial?: Partial<EventDraft>; onConfirmed?: (draft: EventDraft) => Promise<void>; onSaved: (event: EventRecord) => void; onCancel: () => void }) {
  const zone = current?.timezone ?? initial?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [draft, setDraft] = useState<EventDraft>(current ?? { title: '', description: '', kind: 'other', context_id: null, local_date: '', starts_at: null, ends_at: null, reminder: { mode: 'default' }, ...initial, timezone: zone });
  const [timed, setTimed] = useState(!!(current?.starts_at ?? initial?.starts_at));
  const [start, setStart] = useState(localTime(current?.starts_at ?? initial?.starts_at ?? null, zone));
  const [end, setEnd] = useState(localTime(current?.ends_at ?? initial?.ends_at ?? null, zone));
  const [preview, setPreview] = useState<TemporalPreview | null>(null);
  const [choice, setChoice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const operation = useRef(crypto.randomUUID());
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  function invalidate() { setPreview(null); setChoice(''); operation.current = crypto.randomUUID(); }
  async function check() {
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try {
      const result = await events.preview({ timezone: draft.timezone, reminder: draft.reminder, ...(timed ? { local_start: start, local_end: end || null } : { local_date: draft.local_date }) }, controller.signal);
      if (!controller.signal.aborted) { setPreview(result); setChoice(result.requires_choice ? '' : '0'); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to check dates.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function save() {
    if (!preview || choice === '' || busy) return;
    const selected = preview.choices[Number(choice)];
    if (!selected) return;
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try {
      const confirmed = { ...draft, local_date: timed ? null : draft.local_date, starts_at: selected.starts_at, ends_at: selected.ends_at };
      if (onConfirmed) { await onConfirmed(confirmed); return; }
      const result = await events.save(confirmed, operation.current, controller.signal, current);
      if (!controller.signal.aborted && result.event) onSaved(result.event);
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to save event.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <form className="space-y-4 rounded-xl border border-border p-5" onSubmit={event => { event.preventDefault(); void (preview ? save() : check()); }} onChange={invalidate}>
    <h2 className="text-lg font-medium">{current ? 'Edit event' : 'New event'}</h2>
    <label className="block space-y-1 text-sm">Title<Input required maxLength={200} disabled={busy} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
    <label className="block space-y-1 text-sm">Description<Input maxLength={1000} disabled={busy} value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
    <div className="grid gap-4 sm:grid-cols-2"><label className="block space-y-1 text-sm">Kind<Select disabled={busy} value={draft.kind} onChange={event => setDraft({ ...draft, kind: event.target.value as EventKind })}>{['quiz', 'exam', 'assignment', 'deadline', 'study', 'other'].map(kind => <option key={kind}>{kind}</option>)}</Select></label>
    <label className="block space-y-1 text-sm">Timezone<Input required disabled={busy} value={draft.timezone} onChange={event => setDraft({ ...draft, timezone: event.target.value })} /></label></div>
    <label className="flex gap-2 text-sm"><input type="checkbox" disabled={busy} checked={timed} onChange={event => setTimed(event.target.checked)} />Include a time</label>
    {timed ? <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Start<Input type="datetime-local" required disabled={busy} value={start} onChange={event => setStart(event.target.value)} /></label><label className="text-sm">End (optional)<Input type="datetime-local" disabled={busy} value={end} onChange={event => setEnd(event.target.value)} /></label></div> : <label className="block text-sm">Date<Input type="date" required disabled={busy} value={draft.local_date ?? ''} onChange={event => setDraft({ ...draft, local_date: event.target.value })} /></label>}
    <label className="block text-sm">Reminder<Select aria-label="Reminder" disabled={busy} value={draft.reminder.mode} onChange={event => setDraft({ ...draft, reminder: { mode: event.target.value as 'default' | 'disabled' } })}><option value="default">Use default reminder</option><option value="disabled">No reminder</option>{draft.reminder.mode === 'at' && <option value="at">Keep existing explicit reminder</option>}</Select></label>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {preview?.field_errors.map(issue => <p key={issue.field} role="alert" className="text-sm text-danger">{issue.message}</p>)}
    {preview && preview.choices.length > 0 && <div onChange={event => event.stopPropagation()} className="space-y-2 text-sm">
      {preview.requires_choice && <p>This local time occurs twice. Choose the intended instant.</p>}
      {preview.choices.map((value, index) => <label key={index} className="flex gap-2"><input type="radio" name="instant" value={index} checked={choice === String(index)} onChange={() => setChoice(String(index))} />{value.starts_at ? new Date(value.starts_at).toUTCString() : `${draft.local_date} in ${draft.timezone}`} · {value.reminder_due_at ? `Reminder ${new Date(value.reminder_due_at).toLocaleString()}` : 'No pending reminder'} ({value.reminder_state})</label>)}
    </div>}
    <div className="flex gap-2"><Button type="submit" disabled={busy || !!preview && (choice === '' || preview.field_errors.length > 0)}>{busy ? 'Please wait…' : preview ? 'Save event' : 'Check dates & reminder'}</Button><Button variant="ghost" disabled={busy} onClick={onCancel}>Cancel</Button></div>
  </form>;
}
