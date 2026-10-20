import { usePageRefresh } from '../../hooks/usePageRefresh';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { useEffect, useRef, useState } from 'react';
import { Button } from '../ui';
import { pendingConcepts, reviewConcept, type PendingConcept } from '../../services/learning';
import type { LearningContext } from '../../types/rag';

type ReviewState = {id: string; decision: 'confirm' | 'discard'; bulk: boolean; completed: number; total: number};

export function ConceptReview({ onReviewed, contexts }: { onReviewed: () => void; contexts: LearningContext[] }) {
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<PendingConcept[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<ReviewState | null>(null);
  const [actionError, setActionError] = useState('');
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  usePageRefresh(() => setReload(value => value + 1), !busy, ['learning']);
  useEffect(() => {
    const controller = new AbortController(); setError('');
    void pendingConcepts(controller.signal).then(values => { if (!controller.signal.aborted) setItems(values); }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load topic suggestions.'); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);
  async function review(item: PendingConcept, decision: 'confirm' | 'discard') {
    if (active.current) return;
    const controller = new AbortController(); active.current = controller;
    setBusy({id:item.id, decision, bulk:false, completed:0, total:1}); setActionError('');
    try {
      await reviewConcept(item.id, decision, controller.signal);
      if (!controller.signal.aborted) { setItems(previous => previous.filter(value => value.id!==item.id)); onReviewed(); setReload(value => value + 1); }
    } catch (reason) { if (!controller.signal.aborted) setActionError(reason instanceof ApiError ? reason.message : 'Unable to review this topic.'); }
    finally { if (!controller.signal.aborted) { active.current = null; setBusy(null); } }
  }
  async function confirmAll() {
    if (active.current || !items.length) return;
    const controller = new AbortController(); active.current = controller;
    const selected = [...items]; let completed = 0, failed = 0;
    setBusy({id:'', decision:'confirm', bulk:true, completed, total:selected.length}); setActionError('');
    // Confirm the visible snapshot through the existing idempotent owner-bound
    // action. Keep requests sequential and preserve partial success on failure.
    for (const item of selected) {
      if (controller.signal.aborted) break;
      try {
        await reviewConcept(item.id, 'confirm', controller.signal);
        if (!controller.signal.aborted) setItems(previous => previous.filter(value => value.id !== item.id));
      } catch { if (!controller.signal.aborted) failed++; }
      completed++;
      if (!controller.signal.aborted) setBusy({id:'', decision:'confirm', bulk:true, completed, total:selected.length});
    }
    if (controller.signal.aborted) return;
    active.current = null; setBusy(null);
    if (failed) setActionError('Some suggestions couldn’t be confirmed. Confirmed topics were saved; try the remaining suggestions again.');
    if (completed > failed) { onReviewed(); setReload(value => value + 1); }
  }
  if (loading) return <Skeleton variant="list" rows={2} />;
  if (!items.length && !error && !actionError && !busy) return null;
  return <section aria-label="Concept suggestions" className="workspace-panel space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3"><div className="max-w-xl"><h2 className="text-lg font-medium text-heading">Topic suggestions to review</h2>
      <p className="mt-1 text-sm text-muted">Mentra noticed these topics in your learning activity. Confirm accepts the topic and adds it to its learning area when one is linked. It doesn’t mark it learned or change your score. Dismiss removes the suggestion.</p></div>
      {!!items.length && <Button size="sm" variant="secondary" aria-label="Confirm all suggestions" disabled={!!busy} loading={busy?.bulk} onClick={() => void confirmAll()}>{busy?.bulk ? `Confirming ${busy.completed} of ${busy.total}` : `Confirm all (${items.length})`}</Button>}
    </div>
    <p className="text-xs text-muted">Confirm all applies to the suggestions shown here. More suggestions may appear after these are reviewed.</p>
    {(error || actionError) && <p role="alert" className="text-sm text-danger">{actionError || error} {error && <Button variant="ghost" size="sm" onClick={() => setReload(value => value + 1)}>Retry</Button>}</p>}
    <div className="divide-y divide-border">{items.map(item => <div key={item.id} role="group" aria-label={`Review ${item.label}`} className="flex flex-wrap items-center gap-3 py-3">
      <div className="min-w-0 flex-1"><p className="font-medium text-heading">{item.label}</p><p className="mt-1 text-xs text-muted">{item.context_id ? contexts.find(context => context.context_id === item.context_id)?.name ?? 'Linked learning area' : 'No learning area linked; confirming saves the topic name only.'}</p></div>
      <div className="flex shrink-0 gap-2"><Button size="sm" disabled={!!busy} loading={!busy?.bulk && busy?.id === item.id && busy.decision === 'confirm'} onClick={() => void review(item,'confirm')}>Confirm</Button>
        <Button size="sm" variant="ghost" disabled={!!busy} loading={!busy?.bulk && busy?.id === item.id && busy.decision === 'discard'} onClick={() => void review(item,'discard')}>Dismiss</Button></div>
    </div>)}</div>
  </section>;
}
