import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowUpRight, BookOpen, CheckCircle2, X } from 'lucide-react';
import { Dialog } from '../ui/Dialog';
import { Button, IconButton, buttonStyles } from '../ui';
import { Skeleton } from '../ui/Skeleton';
import { progressExplanation } from '../../services/learning';
import { practiceLink } from '../../services/practiceIntent';
import type { ProgressExplanation } from '../../types/learning';
import { progressStatus } from './progressLabels';

const date = (value: string | null) => value ? new Date(value).toLocaleDateString(undefined, {year:'numeric',month:'short',day:'numeric'}) : 'Not yet recorded';
const participation = { independent: 'Reported independent', repeated: 'Repeated / answer-exposed practice', assisted: 'Assisted practice', unspecified: 'Assistance not specified' };
const outcome = (value: string) => value==='CORRECT' ? 'Correct' : value==='INCORRECT' ? 'Incorrect' : value==='PARTIAL' ? 'Partially correct' : 'Outcome unknown';
export function ProgressEvidence({ concept, context, onClose }: { concept: string; context: string; onClose: () => void }) {
  const [data, setData] = useState<ProgressExplanation>(), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setData(undefined); setError('');
    void progressExplanation(concept, context, controller.signal).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(() => { if (!controller.signal.aborted) setError('Unable to load supporting practice. Try again.'); });
    return () => controller.abort();
  }, [concept, context, retry]);
  const practiceContext = data?.context_id || context;
  return <Dialog open onDismiss={onClose} aria-labelledby="progress-evidence-title" className="m-auto flex max-h-[88dvh] w-[calc(100%-1.5rem)] max-w-2xl flex-col overflow-hidden rounded-panel border border-border bg-popover p-0 text-foreground shadow-overlay">
    <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border p-4 sm:p-5"><div className="min-w-0"><p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-accent"><Activity size={14} aria-hidden="true" />Your learning evidence</p><h2 id="progress-evidence-title" className="text-base font-semibold text-heading">What is this estimate based on?</h2></div><IconButton aria-label="Close evidence details" onClick={onClose}><X size={17} aria-hidden="true" /></IconButton></header>
    <div className="min-h-0 overflow-y-auto overscroll-contain p-4 sm:p-5">
      {error ? <p role="alert" className="text-sm text-danger">{error} <Button size="sm" variant="ghost" onClick={() => setRetry(value => value + 1)}>Retry</Button></p> : !data ? <Skeleton variant="text" rows={7} /> : <div className="space-y-5 text-sm">
        <div className="space-y-3 rounded-panel border border-border bg-surface p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="break-words font-semibold text-heading">{data.name}</h3><span className="workspace-status">{progressStatus(data.knowledge_status)}</span></div>
          <p className="text-xl font-semibold tabular-nums tracking-tight text-heading">{data.mastery === null ? 'Still getting to know this topic' : `${Math.round(data.mastery_lower_bound * 100)}–${Math.round(data.mastery_upper_bound * 100)}% estimated range`}</p>
          <p className="text-xs leading-5 text-muted">{data.mastery === null ? 'A few independent answers will help build an initial picture.' : 'A wider range means more uncertainty. More varied, independent practice gives the estimate stronger support.'}</p>
        </div>
        <dl className="grid grid-cols-2 gap-3">{[
          ['Recent independent items',String(data.independent_item_count)], ['Accepted practice observations',String(data.evidence_count)],
          ['Last accepted practice',date(data.last_practice_at)], ['Last independent practice',date(data.last_independent_at)],
        ].map(([label,value]) => <div key={label} className="min-w-0 rounded-control border border-border p-3"><dt className="text-[11px] leading-4 text-muted">{label}</dt><dd className="mt-1.5 break-words text-sm font-medium text-heading">{value}</dd></div>)}</dl>
        <section aria-label="Independent difficulty coverage"><h3 className="font-medium text-heading">Practice across difficulty levels</h3><p className="mt-1 text-xs text-muted">Recent independent questions at each level.</p><div className="mt-3 grid grid-cols-3 gap-2">{data.difficulty_coverage.map(item => <div key={item.band} className="rounded-control bg-surface p-3"><p className="text-[11px] capitalize text-muted">{item.band==='hard' ? 'Challenging' : item.band}</p><p className="mt-1 font-semibold tabular-nums text-heading">{item.independent_items}<span className="ml-1 text-[10px] font-normal text-muted">items</span></p></div>)}</div></section>
        <section aria-label="Recent accepted practice"><h3 className="font-medium text-heading">Recent accepted practice</h3>{!data.recent_evidence.length ? <div className="mt-3 rounded-control border border-dashed border-border p-4 text-center"><BookOpen size={22} className="mx-auto text-subtle" aria-hidden="true" /><p className="mt-2 text-xs text-muted">No accepted evidence yet. Confirming a topic adds no mastery evidence.</p></div> : <ul className="mt-3 divide-y divide-border rounded-control border border-border">{data.recent_evidence.map((item, index) => <li key={index} className="space-y-2 p-3"><div className="flex items-start gap-2.5"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-subtle" aria-hidden="true" /><div className="min-w-0"><p className="break-words text-xs leading-5 text-heading">{participation[item.participation]} · {outcome(item.result)}</p><p className="mt-0.5 text-[11px] text-muted">{date(item.occurred_at)}{(item.grade_revision ?? 0)>1 ? ' · Updated results' : ''}</p></div></div>{item.source_available ? <Link className="inline-flex min-h-8 items-center gap-1 text-xs font-medium text-accent underline underline-offset-2 focus-visible:ring-2 focus-visible:ring-accent" to={`/assessments?assessment=${encodeURIComponent(item.assessment_id!)}&attempt=${encodeURIComponent(item.attempt_id!)}`}>Open assessment results<ArrowUpRight size={13} aria-hidden="true" /></Link> : item.assessment_id ? <p className="text-xs leading-5 text-muted">Source unavailable or has newer results. The accepted observation remains in your learning history.</p> : null}</li>)}</ul>}</section>
        <details className="rounded-control bg-surface p-3 text-xs leading-5 text-muted"><summary className="cursor-pointer font-medium text-heading focus-visible:ring-2 focus-visible:ring-accent">How to read these estimates</summary><div className="mt-2 space-y-2"><p>These are heuristic learning indicators, not calibrated probabilities or exam grades. Recall confidence changes with time since demonstrated practice.</p><p>Assisted, repeated and unspecified work can be recorded as practice without establishing independent mastery. Corrections replace earlier accepted observations.</p><p>Independent item counts reflect a recent window of up to 64 items. This list shows the five most recent accepted observations.</p></div></details>
      </div>}
    </div>
    {data && <footer className="shrink-0 space-y-3 border-t border-border bg-surface p-4 sm:p-5"><div><p className="text-xs font-semibold text-heading">Suggested next check</p><p className="mt-1 text-xs leading-5 text-muted">{data.next_check}</p></div>{practiceContext && <Link className={buttonStyles({variant:'secondary',size:'sm',className:'w-full sm:w-auto'})} to={practiceLink({ context_id:practiceContext, concept_ids:[data.concept_id], topic:data.name, purpose:'verification' })}>Prepare new questions<ArrowUpRight size={14} aria-hidden="true" /></Link>}</footer>}
  </Dialog>;
}
