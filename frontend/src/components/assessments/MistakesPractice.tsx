import { AnswerContent } from '../content/AnswerContent';
import { selectedAnswer } from './AssessmentPaper';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, CheckCircle2, RotateCcw, Sparkles } from 'lucide-react';
import { Button, Select, buttonStyles } from '../ui';
import { Skeleton } from '../ui/Skeleton';
import { MarkdownContent } from '../content/MarkdownContent';
import { WorkspaceEmpty } from '../workspace/WorkspaceHeader';
import { AssessmentGenerationCard } from './AssessmentGenerationCard';
import { assessments } from '../../services/assessments';
import { ApiError } from '../../services/api';
import { usePageRefresh } from '../../hooks/usePageRefresh';
import type { MistakesPage } from '../../types/assessments';

export function MistakesPractice() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const selectedAssessments = params.getAll('mistake_assessment'), topics = params.getAll('mistake_topic');
  const key = JSON.stringify([selectedAssessments, topics]);
  const [page, setPage] = useState<MistakesPage>();
  const [loadedKey, setLoadedKey] = useState('');
  const [facets, setFacets] = useState<Pick<MistakesPage, 'topics' | 'assessments'>>({ topics: [], assessments: [] });
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0), [offset, setOffset] = useState(0);
  const queryKey = JSON.stringify([key, offset]);
  const [count, setCount] = useState('5');
  const active = useRef<AbortController>();
  const lock = useRef(false), operation = useRef<{ payload: string; id: string }>();
  const job = params.get('revision_job');
  useEffect(() => () => active.current?.abort(), []);
  usePageRefresh(() => setReload(value => value + 1), !busy && !job, ['assessments']);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    void assessments.mistakes(selectedAssessments, topics, offset, controller.signal).then(value => {
      if (!controller.signal.aborted) { setPage(value); setLoadedKey(queryKey); setFacets(value); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load your mistakes.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [key, offset, reload]);
  function filter(name: string, values: string[]) {
    const next = new URLSearchParams(params); next.delete(name); values.forEach(value => next.append(name, value));
    setPage(undefined); setOffset(0); setParams(next);
  }
  async function create() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    const body = { assessment_ids: selectedAssessments, topic_ids: topics, count: Number(count) };
    const payload = JSON.stringify(body);
    if (operation.current?.payload !== payload) operation.current = { payload, id: crypto.randomUUID() };
    const controller = new AbortController(); active.current = controller;
    try {
      const result = await assessments.reviseMistakes({ ...body, client_request_id: operation.current.id }, controller.signal);
      if (!controller.signal.aborted) { const next = new URLSearchParams(params); next.set('revision_job', result.id); setParams(next); operation.current = undefined; }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to prepare revision practice. Try again.'); }
    finally { lock.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  return <div className="space-y-5">
    <section className="workspace-panel space-y-5">
      <div className="flex items-start gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-control bg-active text-accent"><RotateCcw size={20} aria-hidden="true" /></span><div className="min-w-0"><h2 className="text-lg font-medium text-heading">Turn mistakes into progress</h2><p className="mt-1 text-sm leading-6 text-muted">Revisit the questions that need another try. Mentra prioritizes repeated mistakes and larger score gaps, then creates fresh variations in a shuffled order.</p></div></div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="space-y-1.5 text-sm font-medium text-heading"><span>Topics</span><Select multiple aria-label="Mistake topics" value={topics} disabled={busy || !!job} onChange={event => filter('mistake_topic', Array.from(event.target.selectedOptions, option => option.value))}>{facets.topics.map(topic => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</Select><span className="block text-xs font-normal text-muted">Leave empty to include all topics.</span></label>
        <label className="space-y-1.5 text-sm font-medium text-heading"><span>Assessments</span><Select multiple aria-label="Mistake assessments" value={selectedAssessments} disabled={busy || !!job} onChange={event => filter('mistake_assessment', Array.from(event.target.selectedOptions, option => option.value))}>{facets.assessments.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</Select><span className="block text-xs font-normal text-muted">Select one or more, or leave empty for all.</span></label>
      </div>
      <div className="flex flex-wrap items-end justify-between gap-3 border-t border-border pt-4"><label className="space-y-1.5 text-xs text-muted"><span>Questions per revision</span><Select aria-label="Revision question count" value={count} disabled={busy || !!job} onChange={event => setCount(event.target.value)}>{[5, 10, 15, 20].map(value => <option key={value} value={value}>Up to {value} questions</option>)}</Select></label><Button className="max-sm:w-full" loading={busy} disabled={busy || loading || !!job || !page?.active_count} onClick={() => void create()}><Sparkles size={16} aria-hidden="true" />{selectedAssessments.length || topics.length ? 'Practice selected' : 'Practice my mistakes'}</Button></div>
      <p className="text-xs leading-5 text-muted">Each new assessment is tagged “Revision assessment” and retains its source records. Revision counts as repeated practice, not independent mastery evidence.</p>
    </section>
    {job && <div className="space-y-3"><Button variant="ghost" size="sm" onClick={() => { const next = new URLSearchParams(params); next.delete('revision_job'); setParams(next); }}>Back to mistake history</Button><AssessmentGenerationCard key={job} id={job} title="Revision assessment" onComplete={result => navigate(`/assessments?assessment=${encodeURIComponent('assessment' in result ? result.assessment.id : result.id)}`)} /></div>}
    {error && <div role="alert" className="workspace-panel flex flex-wrap items-center gap-3 text-sm text-danger">{error}<Button variant="secondary" size="sm" onClick={() => setReload(value => value+1)}>Refresh mistakes</Button></div>}
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-medium text-heading">Your mistake history</h2>{page && <p className="text-xs text-muted">{page.active_count} to revisit · {page.total - page.active_count} corrected</p>}</div>
    {loading && (!page || loadedKey !== queryKey) ? <Skeleton variant="list" /> : page?.total === 0 ? <WorkspaceEmpty icon={CheckCircle2} title="Nothing to revisit here" description="Mistakes and partial answers from graded assessments will appear here. Try different filters if you expected more." /> : <ul className="space-y-3">{page?.items.map(item => <li key={item.id} className="workspace-panel space-y-3">
      <div className="flex flex-wrap items-center gap-2"><span className="workspace-status">{item.resolved ? 'Corrected in later practice' : item.priority}</span>{item.topics.map(topic => <span key={topic.id} className="text-xs text-muted">{topic.name}</span>)}<span className="ml-auto text-xs tabular-nums text-muted">{item.score}/{item.marks} · {item.occurrences} {item.occurrences === 1 ? 'mistake' : 'mistakes'}</span></div>
      <div className="min-w-0 break-words text-sm"><MarkdownContent content={item.prompt} /></div>
      {item.context && <details><summary className="ui-disclosure cursor-pointer text-xs text-muted">Question context</summary><MarkdownContent content={item.context} /></details>}
      <AnswerContent content={selectedAnswer(item, item.answer)} />
      <div className="rounded-control bg-surface p-3 text-sm text-muted"><MarkdownContent content={item.feedback} /></div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3"><Link className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'max-w-full text-left' })} to={`/assessments?assessment=${encodeURIComponent(item.assessment_id)}&attempt=${encodeURIComponent(item.attempt_id)}`}><span className="min-w-0 break-words">{item.assessment_title}</span><ArrowUpRight size={14} className="shrink-0" aria-hidden="true" /></Link><time className="text-xs text-subtle" dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleDateString()}</time></div>
    </li>)}</ul>}
    {page && (offset > 0 || page.next_offset !== null) && <div className="flex justify-between gap-2"><Button variant="secondary" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset-30))}>Previous</Button><Button variant="secondary" disabled={loading || page.next_offset === null} onClick={() => setOffset(page.next_offset!)}>Next</Button></div>}
  </div>;
}
