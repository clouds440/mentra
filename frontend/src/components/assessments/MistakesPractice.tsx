import { QuestionCardPreview } from './QuestionCardPreview';
import { PageSection } from '../workspace/PageShell';
import { AnswerContent } from '../content/AnswerContent';
import { selectedAnswer } from './AssessmentPaper';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, CheckCircle2, Sparkles, X } from 'lucide-react';
import { Button, Select, Dialog, IconButton, Pagination, buttonStyles } from '../ui';
import { ViewToggle } from '../ui/ViewToggle';
import { Skeleton } from '../ui/Skeleton';
import { MarkdownContent } from '../content/MarkdownContent';
import { WorkspaceEmpty } from '../workspace/WorkspaceHeader';
import { AssessmentGenerationCard } from './AssessmentGenerationCard';
import { assessments } from '../../services/assessments';
import { ApiError } from '../../services/api';
import { invalidatePageCache } from '../../services/pageCache';
import { usePageRefresh } from '../../hooks/usePageRefresh';
import type { MistakesPage, MistakeItem } from '../../types/assessments';

export function MistakesPractice() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const selectedAssessments = params.getAll('mistake_assessment'), topics = params.getAll('mistake_topic');
  const contexts = params.getAll('mistake_context');
  const key = JSON.stringify([selectedAssessments, topics, contexts]);
  const [practiceOpen, setPracticeOpen] = useState(false);
  const [reviewed, setReviewed] = useState<MistakeItem>();
  const listView = params.get('mistake_view') === 'list';
  const [page, setPage] = useState<MistakesPage>();
  const [loadedKey, setLoadedKey] = useState('');
  const [facets, setFacets] = useState<Pick<MistakesPage, 'topics' | 'assessments' | 'contexts'>>({ topics: [], assessments: [], contexts: [] });
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const requestedOffset = Number(params.get('mistake_offset'));
  const offset = Number.isSafeInteger(requestedOffset) && requestedOffset > 0 ? Math.floor(requestedOffset / 10) * 10 : 0;
  function setOffset(value: number) { const next = new URLSearchParams(params); next.set('mistake_offset', String(value)); setParams(next); }
  const queryKey = JSON.stringify([key, offset]);
  const [count, setCount] = useState('5');
  const active = useRef<AbortController>();
  const lock = useRef(false), operation = useRef<{ payload: string; id: string }>();
  const job = params.get('revision_job');
  useEffect(() => () => active.current?.abort(), []);
  usePageRefresh(() => setReload(value => value + 1), !busy && !job, ['assessments']);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    void assessments.mistakes(selectedAssessments, topics, offset, controller.signal, contexts).then(value => {
      if (!controller.signal.aborted) { setPage(value); setLoadedKey(queryKey); setFacets(value); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load your mistakes.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [key, offset, reload]);
  function filter(name: string, values: string[]) {
    const next = new URLSearchParams(params); next.delete(name); values.forEach(value => next.append(name, value));
    next.delete('mistake_offset'); setParams(next);
  }
  async function create() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    const body = { assessment_ids: selectedAssessments, topic_ids: topics, context_ids: contexts, count: Number(count) };
    const payload = JSON.stringify(body);
    if (operation.current?.payload !== payload) operation.current = { payload, id: crypto.randomUUID() };
    const controller = new AbortController(); active.current = controller;
    try {
      const result = await assessments.reviseMistakes({ ...body, client_request_id: operation.current.id }, controller.signal);
      if (!controller.signal.aborted) { const next = new URLSearchParams(params); next.set('revision_job', result.id); setParams(next); setPracticeOpen(false); operation.current = undefined; }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to prepare revision practice. Try again.'); }
    finally { lock.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  function filters() {
    return <div className="grid gap-3 sm:grid-cols-3">{[
      {label:'Learning context', name:'mistake_context', aria:'Mistake learning contexts', values:contexts, options:(facets.contexts ?? []).map(x => ({id:x.id, label:x.name}))},
      {label:'Assessment', name:'mistake_assessment', aria:'Mistake assessments', values:selectedAssessments, options:facets.assessments.map(x => ({id:x.id, label:x.title}))},
      {label:'Topic', name:'mistake_topic', aria:'Mistake topics', values:topics, options:facets.topics.map(x => ({id:x.id, label:x.name}))},
    ].map(field => <label key={field.name} className="space-y-1.5 text-xs font-medium text-muted"><span>{field.label}</span><Select multiple aria-label={field.aria} value={field.values} disabled={busy} onChange={event => filter(field.name, Array.from(event.target.selectedOptions, option => option.value))}>{field.options.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Select></label>)}</div>;
  }
  const current = loadedKey === queryKey ? page : undefined;
  return <PageSection className="space-y-5">
    {practiceOpen && <Dialog open busy={busy} onDismiss={() => setPracticeOpen(false)} aria-labelledby="mistake-practice-title" className="max-w-2xl">
      <div className="mb-5 flex items-center justify-between gap-3"><h2 id="mistake-practice-title" className="text-lg font-medium text-heading">Practice my mistakes</h2><IconButton aria-label="Close practice options" disabled={busy} onClick={() => setPracticeOpen(false)}><X size={18} /></IconButton></div>
      <p className="mb-5 text-sm leading-6 text-muted">Choose what to revisit, or leave filters empty to include everything. Mentra prioritizes repeated mistakes and creates fresh variations.</p>
      <form className="space-y-5" onSubmit={event => { event.preventDefault(); void create(); }}>
        {filters()}
      {(contexts.length > 0 || selectedAssessments.length > 0 || topics.length > 0) && <Button variant="ghost" size="sm" disabled={busy} onClick={() => { const next = new URLSearchParams(params); ['mistake_context', 'mistake_assessment', 'mistake_topic', 'mistake_offset'].forEach(name => next.delete(name)); setParams(next); }}>Clear filters</Button>}
        <label className="block space-y-1.5 text-xs font-medium text-muted"><span>Questions per revision</span><Select aria-label="Revision question count" value={count} disabled={busy} onChange={event => setCount(event.target.value)}>{[5, 10, 15, 20].map(value => <option key={value} value={value}>Up to {value} questions</option>)}</Select></label>
        <p className="text-xs leading-5 text-muted">Revision assessments retain their source records and count as repeated practice.</p>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        {current?.active_count === 0 && <p className="text-sm text-muted">No unresolved mistakes match these filters.</p>}
        <div className="flex flex-wrap justify-end gap-2"><Button type="button" variant="secondary" disabled={busy} onClick={() => setPracticeOpen(false)}>Cancel</Button><Button type="submit" loading={busy} disabled={busy || loading || !current?.active_count}><Sparkles size={16} aria-hidden="true" />Generate practice</Button></div>
      </form>
    </Dialog>}
    {job && <div className="space-y-3"><Button variant="ghost" size="sm" onClick={() => { const next = new URLSearchParams(params); next.delete('revision_job'); setParams(next); }}>Back to mistake history</Button><AssessmentGenerationCard key={job} id={job} title="Revision assessment" onComplete={result => navigate(`/assessments?assessment=${encodeURIComponent('assessment' in result ? result.assessment.id : result.id)}`)} /></div>}
    {error && !practiceOpen && <div role="alert" className="workspace-panel flex flex-wrap items-center gap-3 text-sm text-danger">{error}<Button variant="secondary" size="sm" onClick={() => { invalidatePageCache(['assessments']); setReload(value => value+1); }}>Refresh mistakes</Button></div>}
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-medium text-heading">Your mistake history</h2><p className="mt-1 text-xs text-muted">Most recent first{current ? ` · ${current.active_count} to revisit · ${current.total - current.active_count} corrected` : ''}</p></div><div className="flex flex-wrap items-center gap-2"><Button disabled={!!job} onClick={() => setPracticeOpen(true)}><Sparkles size={16} aria-hidden="true" />Practice my mistakes</Button><ViewToggle label="Mistake view" view={listView ? 'list' : 'grid'} onChange={value => { const next = new URLSearchParams(params); next.set('mistake_view', value === 'list' ? 'list' : 'cards'); setParams(next, {replace:true}); }} /></div></div>
    {loading && (!page || loadedKey !== queryKey) ? <Skeleton variant="list" /> : current?.total === 0 ? <WorkspaceEmpty icon={CheckCircle2} title="Nothing to revisit here" description="Mistakes and partial answers from graded assessments will appear here. Try different filters if you expected more." /> : <ul className={listView ? "overflow-hidden rounded-panel border border-border bg-card divide-y divide-border" : "workspace-compact-grid"}>{current?.items.map(item => <li key={item.id} className={listView ? "space-y-2 p-4" : "workspace-panel flex h-56 min-w-0 flex-col gap-3 overflow-hidden"}>
      {listView ? <>
      <div className="flex flex-wrap items-center gap-2"><span className="workspace-status">{item.resolved ? 'Corrected in later practice' : item.priority}</span>{item.topics.map(topic => <span key={topic.id} className="text-xs text-muted">{topic.name}</span>)}<span className="ml-auto text-xs tabular-nums text-muted">{item.score}/{item.marks} · {item.occurrences} {item.occurrences === 1 ? 'mistake' : 'mistakes'}</span></div>
      <div className="min-w-0 break-words text-sm"><MarkdownContent content={item.prompt} /></div>
      <MistakeFeedback item={item} />
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3"><Link className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'max-w-full text-left' })} to={`/assessments?assessment=${encodeURIComponent(item.assessment_id)}&attempt=${encodeURIComponent(item.attempt_id)}`}><span className="min-w-0 break-words">{item.assessment_title}</span><ArrowUpRight size={14} className="shrink-0" aria-hidden="true" /></Link><time className="text-xs text-subtle" dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleDateString()}</time></div>
</> : <>
      <div className="flex min-w-0 items-center justify-between gap-2"><span className="truncate text-xs text-muted">{item.resolved ? 'Corrected' : item.priority}</span><span className="shrink-0 text-xs tabular-nums text-muted">{item.score}/{item.marks}</span></div>
      <QuestionCardPreview content={item.prompt} />
      <QuestionCardPreview content={item.feedback} secondary />
      <p className="truncate text-xs text-subtle" title={item.assessment_title}>{item.assessment_title}</p>
      <Button variant="secondary" size="sm" className="mt-auto w-full" onClick={() => setReviewed(item)}>Review mistake<ArrowUpRight size={14} aria-hidden="true" /></Button>
</>}
    </li>)}</ul>}
    {reviewed && <Dialog open onDismiss={() => setReviewed(undefined)} aria-labelledby="mistake-review-title" className="max-w-2xl">
      <div className="mb-4 flex items-center justify-between gap-3"><h2 id="mistake-review-title" className="font-medium text-heading">Review mistake</h2><IconButton aria-label="Close mistake review" onClick={() => setReviewed(undefined)}><X size={18} /></IconButton></div>
      <div className="min-w-0 space-y-4 break-words text-sm"><MarkdownContent content={reviewed.prompt} /><MistakeFeedback item={reviewed} /><Link className={buttonStyles({variant:'secondary',size:'sm',className:'max-w-full'})} to={`/assessments?assessment=${encodeURIComponent(reviewed.assessment_id)}&attempt=${encodeURIComponent(reviewed.attempt_id)}`}><span className="truncate">{reviewed.assessment_title}</span><ArrowUpRight size={14} aria-hidden="true" /></Link></div>
    </Dialog>}
    {current && <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-xs tabular-nums text-muted">{current.total ? `${offset + 1}–${Math.min(offset + 10, current.total)} of ${current.total}` : '0 mistakes'}</p><Pagination page={Math.floor(offset / 10) + 1} pages={Math.ceil(current.total / 10)} disabled={loading} onChange={value => setOffset((value - 1) * 10)} label="Mistake history pages" /></div>}

  </PageSection>;
}

function MistakeFeedback({item}: {item: MistakeItem}) {
  return <>
    {item.context && <details><summary className="ui-disclosure cursor-pointer text-xs text-muted">Question context</summary><MarkdownContent content={item.context} /></details>}
    <AnswerContent content={selectedAnswer(item, item.answer)} />
    <div className="rounded-control bg-surface p-3 text-sm text-muted"><MarkdownContent content={item.feedback} /></div>
  </>;
}
