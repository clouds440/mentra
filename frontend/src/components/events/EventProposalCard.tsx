import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../ui/Button';
import { EventEditor } from './EventEditor';
import { eventProposals } from '../../services/eventProposals';
import type { EventProposal, EventDraft } from '../../types/events';

export function EventProposalCard({ initial }: { initial: EventProposal }) {
  const [value, setValue] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    void eventProposals.detail(initial.id, request.signal).then(result => { if (!request.signal.aborted) setValue(result); }).catch(reason => { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : 'Proposal unavailable.'); });
    return () => controller.current?.abort();
  }, [initial.id]);
  async function decide(decision: 'approve' | 'dismiss', details?: EventDraft) {
    controller.current?.abort(); const request = new AbortController(); controller.current = request; setBusy(true); setError('');
    try {
      const result = await eventProposals.decide(value, decision, request.signal, details);
      if (!request.signal.aborted) { setValue(result); setEditing(false); }
    } catch (reason) {
      if (!request.signal.aborted) { setError(reason instanceof Error ? reason.message : 'Unable to save decision.');
        const refreshed = await eventProposals.detail(value.id, request.signal).catch(() => null);
        if (refreshed && !request.signal.aborted) setValue(refreshed);
      }
      throw reason;
    } finally { if (!request.signal.aborted) setBusy(false); }
  }
  const pending = value.state === 'pending' || value.state === 'deciding';
  return <section aria-label="Event proposal" className="my-4 space-y-3 rounded-xl border border-border bg-surface p-4">
    <h3 className="font-medium text-heading">{value.candidate?.title ?? `Update event: ${value.status}`}</h3>
    <p className="text-sm text-muted">{value.candidate?.local_date ?? value.candidate?.starts_at ?? 'Date needs review'} · {value.candidate?.timezone ?? 'Timezone needs review'}</p>
    <p className="text-sm text-muted">{value.uncertainty}</p><blockquote className="border-l border-border pl-3 text-sm">{value.quote}</blockquote>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {!pending && <p role="status" className="text-sm">{value.state === 'approved' ? 'Event saved.' : `Proposal ${value.state}.`}</p>}
    {value.event_id && <Link className="text-sm text-accent underline" to={`/progress?tab=events&event=${value.event_id}`}>View event</Link>}
    {pending && !editing && <div className="flex flex-wrap gap-2">
      <Button size="sm" disabled={busy} onClick={() => { if (value.action === 'status') void decide('approve').catch(() => {}); else setEditing(true); }}>{value.action === 'create' ? 'Add event' : 'Review update'}</Button>
      {value.action !== 'status' && <Button variant="secondary" size="sm" disabled={busy} onClick={() => setEditing(true)}>Edit details</Button>}
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => void decide('dismiss').catch(() => {})}>Dismiss</Button>
    </div>}
    {pending && editing && <EventEditor initial={value.candidate ?? {}} onSaved={() => {}} onConfirmed={draft => decide('approve', draft)} onCancel={() => setEditing(false)} />}
  </section>;
}
