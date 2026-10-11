import { usePageRefresh } from '../../hooks/usePageRefresh';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { useEffect, useRef, useState } from 'react';
import { Button } from '../ui';
import { pendingConcepts, reviewConcept, type PendingConcept } from '../../services/learning';

export function ConceptReview({ onReviewed }: { onReviewed: () => void }) {
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<PendingConcept[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const active = useRef<AbortController | null>(null);
  usePageRefresh(() => setReload(value => value + 1), !busy);
  useEffect(() => {
    const controller = new AbortController(); active.current=controller;
    void pendingConcepts(controller.signal).then(setItems).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load concept suggestions.'); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);
  async function review(item: PendingConcept, decision: 'confirm' | 'discard') {
    const controller=active.current;
    if (!controller || controller.signal.aborted) return;
    setBusy(item.id); setError('');
    try {
      await reviewConcept(item.id, decision, controller.signal);
      if (!controller.signal.aborted) { setItems(previous => previous.filter(value => value.id!==item.id)); onReviewed(); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to review this concept.'); }
    finally { if (!controller.signal.aborted) setBusy(''); }
  }
  if (loading) return <Skeleton variant="list" rows={2} />;
  if (!items.length && !error) return null;
  return <section aria-label="Concept suggestions" className="workspace-panel space-y-3"><h2 className="text-lg font-medium">Concepts to review</h2><p className="text-sm text-muted">Confirm a suggested concept before adding it to your learning context.</p>{error && <p role="alert" className="text-sm text-danger">{error}</p>}{items.map(item => <div key={item.id} className="flex flex-wrap items-center gap-3"><span className="flex-1">{item.label}</span><Button size="sm" disabled={!!busy} loading={busy === item.id} onClick={() => void review(item,'confirm')}>Confirm</Button><Button size="sm" variant="ghost" disabled={!!busy} loading={busy === item.id} onClick={() => void review(item,'discard')}>Dismiss</Button></div>)}</section>;
}
