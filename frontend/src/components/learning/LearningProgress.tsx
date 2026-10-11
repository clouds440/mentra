import { TrendingUp, CalendarDays, BookOpen, Compass, ArrowUpRight } from 'lucide-react';
import { WorkspaceHeader, WorkspaceEmpty } from '../workspace/WorkspaceHeader';
import { usePageRefresh, refreshPage } from '../../hooks/usePageRefresh';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { EventAgenda } from '../events/EventAgenda';
import { ConceptReview } from './ConceptReview';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button, Select } from '../ui';
import { EventProposalCard } from '../events/EventProposalCard';
import { eventProposals } from '../../services/eventProposals';
import { learningOverview } from '../../services/learning';
import { listContexts } from '../../services/rag';
import type { EventProposal } from '../../types/events';
import type { LearningOverview } from '../../types/learning';
import type { LearningContext } from '../../types/rag';

export function LearningProgress() { const { identity } = useAuth(); return <Progress key={identity?.learner_id} />; }
function Progress() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'events' ? 'events' : 'learning';
  const [context, setContext] = useState('');
  const [contexts, setContexts] = useState<LearningContext[]>([]);
  const [learning, setLearning] = useState<LearningOverview | null>(null);
  const [proposals, setProposals] = useState<EventProposal[] | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  usePageRefresh(() => setReload(value => value + 1), true);
  useEffect(() => {
    const controller = new AbortController(); setError('');
    if (tab === 'learning') { void Promise.all([learningOverview(controller.signal, context || undefined), listContexts(controller.signal)]).then(([data, choices]) => { if (!controller.signal.aborted) { setLearning(data); setContexts(choices); } }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load learning progress.'); }); }
    else { void eventProposals.list(controller.signal).then(values => { if (!controller.signal.aborted) setProposals(values); }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load event proposals.'); }); }
    return () => controller.abort();
  }, [tab, context, reload]);
  const percent = (value: number | null) => value === null ? 'Unknown' : `${Math.round(value * 100)}%`;
  return <div className="h-full overflow-y-auto"><div className="page-container">
    <WorkspaceHeader title={tab === 'events' ? 'Events' : 'Progress'} description={tab === 'events' ? 'Make room for your next learning milestone. Keep deadlines, practice and study sessions together.' : 'See what you’ve learned, where you’re growing, and what to explore next.'} icon={tab === 'events' ? CalendarDays : TrendingUp} />
    <div role="tablist" aria-label="Progress sections" className="workspace-tabs" onKeyDown={event => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 'learning' : event.key === 'End' ? 'events' : tab === 'learning' ? 'events' : 'learning'; setParams({ tab: next }); document.getElementById(`progress-${next}`)?.focus(); }
    }}>{(['learning', 'events'] as const).map(value => <button id={`progress-${value}`} key={value} role="tab" aria-selected={value === tab} aria-controls={`progress-panel-${value}`} tabIndex={value === tab ? 0 : -1} className={`border-b-2 px-4 py-3 text-sm focus-visible:ring-2 focus-visible:ring-accent ${value === tab ? 'border-accent' : 'border-transparent text-muted'}`} onClick={() => setParams({ tab: value })}>{value === 'learning' ? 'Learning' : 'Events'}</button>)}</div>
    {error && <p role="alert" className="text-sm text-danger">{error} <Button variant="ghost" size="sm" onClick={() => refreshPage(() => setReload(value => value + 1))}>Retry</Button></p>}
    <section role="tabpanel" id="progress-panel-learning" aria-labelledby="progress-learning" hidden={tab !== 'learning'} className="space-y-6">
      {tab==='learning' && <ConceptReview onReviewed={() => setReload(value => value+1)} />}
      <div className="workspace-toolbar"><div><h2 className="font-medium text-heading">Learning overview</h2><p className="mt-1 text-xs text-muted">Choose the area you want to explore.</p></div><Select className="max-w-sm" aria-label="Learning context" value={context} onChange={event => { setLearning(null); setContext(event.target.value); }}><option value="">Active learning contexts</option>{contexts.map(item => <option key={item.context_id} value={item.context_id}>{item.name}</option>)}</Select></div>
      {!learning && !error && <Skeleton variant="table" />}
      {learning && <><div className="grid gap-3 sm:grid-cols-3">{[['Concepts explored', learning.learner.concepts.length], ['Study suggestions', learning.recommendations.length], ['Ready to review', learning.verification.length]].map(([label, value]) => <div key={String(label)} className="workspace-panel"><p className="text-xs text-muted">{label}</p><p className="mt-3 text-3xl font-medium text-heading">{value}</p></div>)}</div><section className="workspace-panel space-y-4"><h2 className="flex items-center gap-2 text-lg font-medium text-heading"><BookOpen size={19} aria-hidden="true" />Your understanding</h2>{!learning.learner.concepts.length && <WorkspaceEmpty icon={BookOpen} title="Every step builds understanding" description="Practice or complete an assessment to start building your learning profile." action={<Link className="text-sm text-accent hover:underline" to="/assessments?tab=create">Create a practice assessment</Link>} />}
      <div className="overflow-x-auto">{!!learning.learner.concepts.length && <table className="w-full text-left text-sm"><thead className="bg-background text-muted"><tr>{['Concept', 'Status', 'Mastery estimate', 'Estimate confidence', 'Retention confidence'].map(label => <th key={label} className="whitespace-nowrap border-b border-border px-3 py-2 font-medium">{label}</th>)}</tr></thead><tbody>{learning.learner.concepts.map(item => <tr key={item.concept_id}><th scope="row" className="border-b border-border px-3 py-3 font-medium">{item.name}</th><td className="border-b border-border px-3 py-3">{item.knowledge_status.replace(/_/g, ' ')}</td><td className="border-b border-border px-3 py-3">{percent(item.mastery)}</td><td className="border-b border-border px-3 py-3">{percent(item.estimate_confidence)}</td><td className="border-b border-border px-3 py-3">{percent(item.retention_confidence)}</td></tr>)}</tbody></table>}</div>
      <p className="text-xs text-muted">These estimates reflect your available learning evidence. Confidence and retention describe different aspects of it.</p></section>
      <section className="space-y-4"><h2 className="flex items-center gap-2 text-lg font-medium text-heading"><Compass size={19} aria-hidden="true" />What to study next</h2><ul className="workspace-grid">{learning.recommendations.map(item => <li key={item.concept_id} className="workspace-item flex flex-col gap-3"><p className="font-medium text-heading">{item.name}</p><p className="text-sm text-muted">{item.reason}</p><Link className="mt-auto inline-flex items-center gap-1.5 text-sm text-accent hover:underline" to={`/?practice=${encodeURIComponent(item.name)}`}>Practice this concept<ArrowUpRight size={14} aria-hidden="true" /></Link></li>)}</ul>
      {!learning.recommendations.length && <p className="text-sm text-muted">Recommendations will appear as evidence becomes available.</p>}</section>
      {!!learning.verification.length && <section className="workspace-panel space-y-3"><h2 className="text-lg font-medium">Check your understanding</h2><ul className="divide-y divide-border">{learning.verification.map(item => <li key={item.concept_id} className="py-2"><span className="font-medium">{item.name}</span><p className="text-sm text-muted">{item.reason}</p></li>)}</ul></section>}
      </>}
    </section>
    <section role="tabpanel" id="progress-panel-events" aria-labelledby="progress-events" hidden={tab !== 'events'} className="space-y-4">{tab === 'events' && <EventAgenda />}<h2 className="border-t border-border pt-6 text-lg font-medium text-heading">For your review</h2>{!proposals && !error && <Skeleton variant="card" />}{proposals?.length === 0 && <p className="text-sm text-muted">No pending proposals.</p>}{proposals?.map(value => <EventProposalCard key={value.id} initial={value} />)}</section>
  </div></div>;
}
