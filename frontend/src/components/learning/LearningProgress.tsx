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
  useEffect(() => {
    const controller = new AbortController(); setError('');
    if (tab === 'learning') { setLearning(null); void Promise.all([learningOverview(controller.signal, context || undefined), listContexts(controller.signal)]).then(([data, choices]) => { if (!controller.signal.aborted) { setLearning(data); setContexts(choices); } }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load learning progress.'); }); }
    else { setProposals(null); void eventProposals.list(controller.signal).then(values => { if (!controller.signal.aborted) setProposals(values); }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load event proposals.'); }); }
    return () => controller.abort();
  }, [tab, context, reload]);
  const percent = (value: number | null) => value === null ? 'Unknown' : `${Math.round(value * 100)}%`;
  return <div className="h-full overflow-y-auto"><div className="page-container">
    <h1 className="page-title">Progress</h1><p className="text-sm text-muted">Your learning evidence, study recommendations and upcoming plans.</p>
    <div role="tablist" aria-label="Progress sections" className="flex gap-2 border-b border-border" onKeyDown={event => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 'learning' : event.key === 'End' ? 'events' : tab === 'learning' ? 'events' : 'learning'; setParams({ tab: next }); document.getElementById(`progress-${next}`)?.focus(); }
    }}>{(['learning', 'events'] as const).map(value => <button id={`progress-${value}`} key={value} role="tab" aria-selected={value === tab} aria-controls={`progress-panel-${value}`} tabIndex={value === tab ? 0 : -1} className={`border-b-2 px-4 py-3 text-sm focus-visible:ring-2 focus-visible:ring-accent ${value === tab ? 'border-accent' : 'border-transparent text-muted'}`} onClick={() => setParams({ tab: value })}>{value === 'learning' ? 'Learning' : 'Events'}</button>)}</div>
    {error && <p role="alert" className="text-sm text-danger">{error} <Button variant="ghost" size="sm" onClick={() => setReload(value => value + 1)}>Retry</Button></p>}
    <section role="tabpanel" id="progress-panel-learning" aria-labelledby="progress-learning" hidden={tab !== 'learning'} className="space-y-6">
      {tab==='learning' && <ConceptReview onReviewed={() => setReload(value => value+1)} />}
      <Select aria-label="Learning context" value={context} onChange={event => setContext(event.target.value)}><option value="">Active learning contexts</option>{contexts.map(item => <option key={item.context_id} value={item.context_id}>{item.name}</option>)}</Select>
      {!learning && !error && <p role="status">Loading learning progress…</p>}
      {learning && <><h2 className="text-lg font-medium">Concepts</h2>{!learning.learner.concepts.length && <p className="text-sm text-muted">No concept evidence yet. Practice or complete an assessment to build your learning profile.</p>}
      <div className="overflow-x-auto">{!!learning.learner.concepts.length && <table className="w-full text-left text-sm"><thead><tr>{['Concept', 'Status', 'Mastery estimate', 'Estimate confidence', 'Retention confidence'].map(label => <th key={label} className="whitespace-nowrap border-b border-border px-3 py-2 font-medium">{label}</th>)}</tr></thead><tbody>{learning.learner.concepts.map(item => <tr key={item.concept_id}><th scope="row" className="border-b border-border px-3 py-3 font-medium">{item.name}</th><td className="border-b border-border px-3 py-3">{item.knowledge_status.replace(/_/g, ' ')}</td><td className="border-b border-border px-3 py-3">{percent(item.mastery)}</td><td className="border-b border-border px-3 py-3">{percent(item.estimate_confidence)}</td><td className="border-b border-border px-3 py-3">{percent(item.retention_confidence)}</td></tr>)}</tbody></table>}</div>
      <p className="text-xs text-muted">Mastery estimates, confidence in those estimates and retention confidence describe different aspects of your evidence.</p>
      <h2 className="text-lg font-medium">What to study next</h2><ul className="space-y-3">{learning.recommendations.map(item => <li key={item.concept_id}><p className="font-medium">{item.name}</p><p className="text-sm text-muted">{item.reason}</p><Link className="text-sm text-accent underline" to={`/?practice=${encodeURIComponent(item.name)}`}>Practice this concept</Link></li>)}</ul>
      {!learning.recommendations.length && <p className="text-sm text-muted">Recommendations will appear as evidence becomes available.</p>}
      {!!learning.verification.length && <><h2 className="text-lg font-medium">Check your understanding</h2><ul>{learning.verification.map(item => <li key={item.concept_id} className="py-2"><span className="font-medium">{item.name}</span><p className="text-sm text-muted">{item.reason}</p></li>)}</ul></>}
      </>}
    </section>
    <section role="tabpanel" id="progress-panel-events" aria-labelledby="progress-events" hidden={tab !== 'events'} className="space-y-4">{tab === 'events' && <EventAgenda />}<h2 className="text-lg font-medium">Pending event proposals</h2>{!proposals && !error && <p role="status">Loading proposals…</p>}{proposals?.length === 0 && <p className="text-sm text-muted">No pending proposals.</p>}{proposals?.map(value => <EventProposalCard key={value.id} initial={value} />)}</section>
  </div></div>;
}
