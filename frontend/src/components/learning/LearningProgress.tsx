import { Tabs } from '../ui/Tabs';
import { TrendingUp, CalendarDays } from 'lucide-react';
import { WorkspaceHeader } from '../workspace/WorkspaceHeader';
import { usePageRefresh, refreshPage } from '../../hooks/usePageRefresh';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { EventAgenda } from '../events/EventAgenda';
import { ConceptReview } from './ConceptReview';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button, Select } from '../ui';
import { EventProposalCard } from '../events/EventProposalCard';
import { eventProposals } from '../../services/eventProposals';
import { learningOverview } from '../../services/learning';
import { listContexts } from '../../services/rag';
import type { EventProposal } from '../../types/events';
import type { LearningOverview } from '../../types/learning';
import type { LearningContext } from '../../types/rag';
import { UnderstandingTable } from './UnderstandingTable';
import { QuickReview } from './QuickReview';
import { LearningSuggestions } from './LearningSuggestions';
import { supportedReview } from './progressLabels';

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
  const [totalConcepts, setTotalConcepts] = useState<number | null>(null);
  usePageRefresh(() => setReload(value => value + 1), true, ['learning', 'learning-contexts', 'event-proposals']);
  useEffect(() => {
    const controller = new AbortController(); setError('');
    if (tab === 'learning') { void Promise.all([learningOverview(controller.signal, context || undefined), listContexts(controller.signal)]).then(([data, choices]) => { if (!controller.signal.aborted) { setLearning(data); setContexts(choices); } }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load learning progress.'); }); }
    else if (tab === 'events') { void eventProposals.list(controller.signal).then(values => { if (!controller.signal.aborted) setProposals(values); }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load event proposals.'); }); }
    return () => controller.abort();
  }, [tab, context, reload]);
  return <div className="h-full overflow-y-auto"><div className="page-container">
    <WorkspaceHeader title={tab === 'events' ? 'Events' : 'Progress'} description={tab === 'events' ? 'Make room for your next learning milestone. Keep deadlines, practice and study sessions together.' : 'See what you’ve learned, where you’re growing, and what to explore next.'} icon={tab === 'events' ? CalendarDays : TrendingUp} />
    <Tabs label="Progress sections" value={tab} onChange={value => { const next = new URLSearchParams(params); next.set('tab', value); if(value !== 'events') next.delete('event'); setParams(next); }} options={(['learning', 'events'] as const).map(value => ({ value, label: value === 'learning' ? 'Learning' : 'Events', id: `progress-${value}`, panel: `progress-panel-${value}` }))} />
    {error && <p role="alert" className="text-sm text-danger">{error} <Button variant="ghost" size="sm" onClick={() => refreshPage(() => setReload(value => value + 1))}>Retry</Button></p>}
    <section role="tabpanel" id="progress-panel-learning" aria-labelledby="progress-learning" hidden={tab !== 'learning'} className="space-y-6">
      {tab==='learning' && <ConceptReview contexts={contexts} onReviewed={() => setReload(value => value+1)} />}
      <div className="workspace-toolbar"><div><h2 className="font-medium text-heading">Learning overview</h2><p className="mt-1 text-xs text-muted">Choose which learning area to explore. Topic suggestions become progress estimates after you practise.</p></div><Select className="max-w-sm" aria-label="Learning context" value={context} onChange={event => { setLearning(null); setTotalConcepts(null); setContext(event.target.value); }}><option value="">Active learning contexts</option>{contexts.map(item => <option key={item.context_id} value={item.context_id}>{item.name}</option>)}</Select></div>
      {!learning && !error && <Skeleton variant="table" />}
      {learning && <><QuickReview learning={learning} context={context} /><div className="grid gap-3 sm:grid-cols-3">{[['Topics in your learning areas', totalConcepts ?? '—'], ['Practice suggestions', learning.recommendations.length], ['Review suggestions', learning.verification.filter(item => supportedReview(item.reason)).length]].map(([label, value]) => <div key={String(label)} className="workspace-panel"><p className="text-xs text-muted">{label}</p><p className="mt-3 text-3xl font-medium text-heading">{value}</p></div>)}</div>
        {tab === 'learning' && <UnderstandingTable key={context} context={context} reload={reload} onTotal={setTotalConcepts} />}
        <LearningSuggestions learning={learning} context={context} />
      </>}
    </section>
    <section role="tabpanel" id="progress-panel-events" aria-labelledby="progress-events" hidden={tab !== 'events'} className="space-y-4">{tab === 'events' && <EventAgenda />}<h2 className="border-t border-border pt-6 text-lg font-medium text-heading">For your review</h2>{!proposals && !error && <Skeleton variant="card" />}{proposals?.length === 0 && <p className="text-sm text-muted">No pending proposals.</p>}{proposals?.map(value => <EventProposalCard key={value.id} initial={value} />)}</section>
  </div></div>;
}
