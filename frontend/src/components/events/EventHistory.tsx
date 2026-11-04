import { useEffect, useRef, useState } from 'react';
import { PageSection } from '../workspace/PageShell';
import { Button } from '../ui';
import { Skeleton } from '../ui/Skeleton';
import { eventProposals } from '../../services/eventProposals';
import { EventProposalCard } from './EventProposalCard';
import type { EventProposal } from '../../types/events';

/** Owner-scoped, paginated decision history; separate from actionable reviews. */
export function EventHistory({ revision }: { revision: string }) {
  const [open, setOpen] = useState(true);
  const [items, setItems] = useState<EventProposal[]>([]);
  const [nextOffset, setNextOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController>();
  async function load(offset = 0) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setLoading(true); setError('');
    try {
      const values = await eventProposals.history(offset, controller.signal);
      if (!controller.signal.aborted) { setItems(current => offset ? [...current, ...values.filter(value => value.state !== 'approved' && !current.some(item => item.id === value.id))] : values.filter(value => value.state !== 'approved')); setNextOffset(values.length === 30 ? offset + values.length : 0); }
    } catch { if (!controller.signal.aborted) setError('Could not load event decisions. Please try again.'); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => { if (open) void load(); return () => request.current?.abort(); }, [open, revision]);
  return <PageSection title="Past decisions" description="Dismissed and expired suggestions stay here. Saved events appear in your agenda."
    actions={<Button variant="secondary" size="sm" onClick={() => setOpen(value => !value)} aria-expanded={open} aria-controls="event-decision-history">{open ? 'Hide history' : 'View history'}</Button>}>
    {open && <div id="event-decision-history" className="space-y-4">
      {error && <div role="alert">{error}<Button variant="ghost" onClick={() => void load()}>Retry</Button></div>}
      {loading && !items.length && <Skeleton variant="list" />}
      {!loading && !error && !items.length && <p className="text-sm text-muted">No past decisions yet.</p>}
      <div className="grid gap-4 lg:grid-cols-2">{items.map(item => <EventProposalCard key={item.id} initial={item} />)}</div>
      {nextOffset > 0 && <Button variant="secondary" disabled={loading} loading={loading} onClick={() => void load(nextOffset)}>Load earlier decisions</Button>}
    </div>}
  </PageSection>;
}
