import { useEffect, useRef, useState } from 'react';
import { Button } from '../ui';
import { pendingConcepts, reviewConcept, type PendingConcept } from '../../services/learning';

export function ConceptReview({ onReviewed }: { onReviewed: () => void }) {
  const [items, setItems] = useState<PendingConcept[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(); active.current=controller;
    void pendingConcepts(controller.signal).then(setItems).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load concept suggestions.'); });
    return () => controller.abort();
  }, []);
  async function review(item: PendingConcept, decision: 'confirm' | 'discard') {
    const controller=active.current;
    if (!controller || controller.signal.aborted) return;
    setBusy(item.id); setError('');
    try {
      await reviewConcept(item.id, decision, controller.signal);
      if (!controller.signal.aborted) { setItems(previous => previous.filter(value => value.id!==item.id)); onReviewed(); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to review this concept.'); }
    finally { if (!controller.signal.aborted) setBusy(''); }
  }
  if (!items.length && !error) return null;
  return <section aria-label="Concept suggestions" className="space-y-3"><h2 className="text-lg font-medium">Concepts to review</h2><p className="text-sm text-muted">Confirm a suggested concept before adding it to your learning context.</p>{error && <p role="alert" className="text-sm text-danger">{error}</p>}{items.map(item => <div key={item.id} className="flex flex-wrap items-center gap-3"><span className="flex-1">{item.label}</span><Button size="sm" disabled={!!busy} onClick={() => void review(item,'confirm')}>Confirm</Button><Button size="sm" variant="ghost" disabled={!!busy} onClick={() => void review(item,'discard')}>Dismiss</Button></div>)}</section>;
}
