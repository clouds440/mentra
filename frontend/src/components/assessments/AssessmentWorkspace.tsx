import { usePageRefresh, refreshPage } from '../../hooks/usePageRefresh';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { AssessmentFeedback } from './AssessmentFeedback';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { Toggle } from '../ui/Toggle';
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button, FileInput, Input, Select } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { assessments } from '../../services/assessments';
import { listContexts, listMaterials } from '../../services/rag';
import type { Assessment, AssessmentAttempt, AssessmentGeneration } from '../../types/assessments';
import type { LearningContext, MaterialDocument } from '../../types/rag';

export function AssessmentWorkspace() { const { identity } = useAuth(); return <Workspace key={identity?.learner_id} />; }
function Workspace() {
  const [params, setParams] = useSearchParams();
  const id = params.get('assessment');
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<Assessment[]>([]);
  const [contexts, setContexts] = useState<LearningContext[]>([]);
  const [documents, setDocuments] = useState<MaterialDocument[]>([]);
  const [current, setCurrent] = useState<Assessment | null>(null);
  const [attempts, setAttempts] = useState<AssessmentAttempt[]>([]);
  const [attempt, setAttempt] = useState<AssessmentAttempt | null>(null);
  const tab = params.get('tab') === 'create' ? 'create' : 'assessments';
  function changeTab(value: 'create' | 'assessments') {
    const next = new URLSearchParams(params);
    if (value === 'create') next.set('tab', value); else next.delete('tab');
    setParams(next);
  }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [more, setMore] = useState<number | null>(null);
  const [draft, setDraft] = useState<AssessmentGeneration>({ client_request_id: crypto.randomUUID(), context_id: '', topic: '', concept_names: [], confirm_new_concepts: false, count: 5, purpose: 'practice', grounded: false, document_ids: [] });
  const [labels, setLabels] = useState('');
  const active = useRef<AbortController | null>(null);
  const startOperation = useRef(crypto.randomUUID());
  usePageRefresh(() => setReload(value => value + 1), !busy && !attempt);
  useEffect(() => {
    const controller = new AbortController(); setLoading(items.length === 0 || !!id && current?.id !== id); setError(''); if (current?.id !== id) { setCurrent(null); setAttempt(null); }
    void Promise.all([assessments.list(controller.signal), listContexts(controller.signal), listMaterials(0, false, controller.signal), id ? assessments.detail(id, controller.signal) : Promise.resolve(null), id ? assessments.attempts(id, controller.signal) : Promise.resolve([])]).then(([page, choices, materials, detail, history]) => {
      if (!controller.signal.aborted) { setItems(page.items); setMore(page.next_offset); setContexts(choices); setDocuments(materials.items); setCurrent(detail); setAttempts(history); if (history[0]?.state !== 'graded') setAttempt(history[0] ?? null); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load assessments.'); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); active.current?.abort(); };
  }, [id, reload]);
  async function generate() {
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try {
      const value = await assessments.generate({ ...draft, concept_names: labels.split(',').map(label => label.trim()).filter(Boolean) }, controller.signal);
      if (!controller.signal.aborted) { setParams({ assessment: value.id }); setDraft(previous => ({ ...previous, client_request_id: crypto.randomUUID() })); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to generate assessment.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function start() {
    if (!current) return;
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try { const result = await assessments.start(current.id, startOperation.current, controller.signal); if (!controller.signal.aborted) { setAttempt(result); setAttempts(previous => [result, ...previous.filter(item => item.id !== result.id)]); startOperation.current = crypto.randomUUID(); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to start attempt.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function loadMore() {
    if (more === null) return; const controller = new AbortController(); active.current = controller;
    try { const result = await assessments.list(controller.signal, more); if (!controller.signal.aborted) { setItems(previous => [...previous, ...result.items]); setMore(result.next_offset); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load more assessments.'); }
  }
  return <div className="h-full overflow-y-auto"><div className="page-container">
    <h1 className="page-title">Assessments</h1>
    <p className="text-sm text-muted">Practice, verify understanding or calibrate specific concepts. Broad onboarding calibration remains separate.</p>
    <div role="tablist" aria-label="Assessment sections" className="flex gap-2 border-b border-border" onKeyDown={event => {
      if (busy || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 'assessments' : event.key === 'End' ? 'create' : tab === 'create' ? 'assessments' : 'create';
      changeTab(next); document.getElementById(`assessment-tab-${next}`)?.focus();
    }}>
      {(['assessments', 'create'] as const).map(value => <button type="button" key={value} id={`assessment-tab-${value}`} role="tab"
        aria-selected={value === tab} aria-controls={`assessment-panel-${value}`} tabIndex={value === tab ? 0 : -1} disabled={busy}
        className={`border-b-2 px-4 py-3 text-sm focus-visible:ring-2 focus-visible:ring-accent ${value === tab ? 'border-accent text-foreground' : 'border-transparent text-muted hover:text-foreground'}`}
        onClick={() => changeTab(value)}>{value === 'create' ? 'Create new' : 'Assessments'}</button>)}
    </div>
    {error && <p role="alert" className="text-sm text-danger">{error} <button className="underline" onClick={() => refreshPage(() => setReload(value => value + 1))}>Refresh</button></p>}
    <section role="tabpanel" id="assessment-panel-create" aria-labelledby="assessment-tab-create" hidden={tab !== 'create'}>
    {loading && !error ? <Skeleton variant="form" rows={5} /> : <form aria-label="Create assessment" className="space-y-4 rounded-xl border border-border p-5" onSubmit={event => { event.preventDefault(); void generate(); }} onChange={() => setDraft(value => ({ ...value, client_request_id: crypto.randomUUID() }))}>
      <label className="block text-sm">Learning context<Select aria-label="Assessment learning context" required disabled={busy} value={draft.context_id} onChange={event => setDraft({ ...draft, context_id: event.target.value })}><option value="">Choose context</option>{contexts.filter(item => item.status !== 'ARCHIVED').map(item => <option key={item.context_id} value={item.context_id}>{item.name}</option>)}</Select></label>
      <label className="block text-sm">Topic<Input required disabled={busy} maxLength={200} value={draft.topic} onChange={event => setDraft({ ...draft, topic: event.target.value })} /></label>
      <label className="block text-sm">Concept names (comma separated, optional)<Input disabled={busy} value={labels} maxLength={1000} onChange={event => setLabels(event.target.value)} /></label>
      <Toggle label="Confirm these names as new learning concepts if needed" disabled={busy} checked={draft.confirm_new_concepts} onChange={event => setDraft({ ...draft, confirm_new_concepts: event.target.checked })} />
      <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Question count<Input type="number" min={1} max={10} disabled={busy} value={draft.count} onChange={event => setDraft({ ...draft, count: Number(event.target.value) })} /></label><label className="text-sm">Purpose<Select aria-label="Assessment purpose" disabled={busy} value={draft.purpose} onChange={event => setDraft({ ...draft, purpose: event.target.value })}><option value="practice">Practice</option><option value="verification">Verification</option><option value="calibration">Granular calibration</option></Select></label></div>
      <Toggle label="Ground questions in selected Library documents" disabled={busy} checked={draft.grounded} onChange={event => setDraft({ ...draft, grounded: event.target.checked })} />
      {draft.grounded && <Select multiple aria-label="Assessment study documents" disabled={busy} value={draft.document_ids} onChange={event => setDraft({ ...draft, document_ids: [...event.target.selectedOptions].map(option => option.value) })}>{documents.filter(item => item.active_generation_id && item.context_ids.includes(draft.context_id)).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</Select>}
      <Button type="submit" disabled={busy} loading={busy}>{'Generate assessment'}</Button>
    </form>}
    </section>
    <section role="tabpanel" id="assessment-panel-assessments" aria-labelledby="assessment-tab-assessments" hidden={tab !== 'assessments'} className="space-y-5">
    {loading && !error && <Skeleton variant="card" />}
    {current && <section className="space-y-5"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-xl font-medium">{current.title}</h2><Button variant="secondary" disabled={busy} loading={busy} onClick={() => void start()}>Start new attempt</Button></div>
      {attempt ? <AnswerSheet key={attempt.id} assessment={current} initial={attempt} onChange={result => { setAttempt(result); setAttempts(previous => [result, ...previous.filter(item => item.id !== result.id)]); }} /> : <ol className="space-y-5">{current.questions.map((question, index) => <li key={question.id}><p className="text-sm text-muted">Question {index+1} · {question.marks} marks</p><MarkdownContent content={question.prompt} /></li>)}</ol>}
      <h3 className="font-medium">Attempt history</h3>{attempts.length === 0 && <p className="text-sm text-muted">No attempts yet.</p>}<ul className="space-y-2">{attempts.map(value => <li key={value.id}><button className="text-sm text-accent underline" onClick={() => setAttempt(value)}>Attempt {value.attempt_number} · {value.state} · {new Date(value.created_at).toLocaleString()}</button></li>)}</ul>
    </section>}
    <h2 className="text-lg font-medium">Your assessments</h2>{!loading && !error && items.length === 0 && <p className="text-sm text-muted">Create your first assessment to begin.</p>}<ul className="divide-y divide-border">{items.map(item => <li key={item.id}><button className="w-full py-4 text-left text-heading hover:text-accent focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setParams({ assessment: item.id })}>{item.title}<span className="ml-2 text-xs text-muted">{item.questions.length} questions · {item.purpose}</span></button></li>)}</ul>{more !== null && <Button variant="secondary" onClick={() => void loadMore()}>Load more</Button>}
    </section>
  </div></div>;
}

export function AnswerSheet({ assessment, initial, onChange }: { assessment: Assessment; initial: AssessmentAttempt; onChange: (attempt: AssessmentAttempt) => void }) {
  const [attempt, setAttempt] = useState(initial);
  const [answers, setAnswers] = useState(initial.state==='pending_transcription' ? initial.extraction?.answers ?? initial.answers : initial.answers);
  const [confirmed, setConfirmed] = useState(false);
  const [assistance, setAssistance] = useState<'unknown' | 'independent' | 'assisted'>(initial.assistance ?? 'unknown');
  const [correcting, setCorrecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  const operation = useRef(crypto.randomUUID());
  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => {
    if (!['submitted', 'grading'].includes(attempt.state) && !(attempt.state==='failed' && attempt.retry_pending)) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>; let polls = 0;
    async function refresh() {
      try { const result = await assessments.attempt(attempt.id, controller.signal); if (!controller.signal.aborted) { setAttempt(result); onChange(result); if ((['submitted','grading'].includes(result.state) || result.state==='failed' && result.retry_pending) && ++polls < 90) timer = setTimeout(() => void refresh(), 2000); } }
      catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to check grading status.'); }
    }
    timer = setTimeout(() => void refresh(), 1000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [attempt.id, attempt.state, attempt.retry_pending]); // eslint-disable-line react-hooks/exhaustive-deps
  const editable = attempt.state === 'draft' || attempt.state === 'pending_transcription' || correcting;
  async function submit() {
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try { const result = await (correcting ? assessments.correct : assessments.submit)(attempt, answers, operation.current, confirmed, controller.signal, assistance); if (!controller.signal.aborted) { setAttempt(result); setCorrecting(false); onChange(result); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to submit answers.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function upload(file: File) {
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try { const result = await assessments.paper(attempt, file, controller.signal); if (!controller.signal.aborted) { setAttempt(result); setAnswers(result.extraction?.answers ?? {}); setConfirmed(false); onChange(result); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to read answer sheet.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section aria-label="Assessment answer sheet" className="space-y-5">
    {attempt.state==='graded' && !correcting && <AssessmentFeedback assessment={assessment} attempt={attempt} />}
    <p className="text-sm text-muted">Attempt {attempt.attempt_number} · {attempt.state}</p>{error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {editable && !correcting && <FileInput label="Upload an answer sheet" aria-label="Upload assessment answer sheet" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value=''; }} />}
    {attempt.extraction && <div className="space-y-2 text-sm text-muted"><p>{attempt.extraction.handwriting_support==='typed_chat' ? 'Your chat answers are ready. Check their question numbers before submitting.' : attempt.extraction.handwriting_support==='vision_requires_review' ? 'Image transcription is ready. Review every answer and its question number before submitting.' : 'Review and correct every extracted answer before submitting. OCR handwriting accuracy is unverified.'}</p>{attempt.extraction.warnings.map((warning,index) => <p key={index}>{warning}</p>)}</div>}
    {(attempt.state !== 'graded' || correcting) && assessment.questions.map((question,index) => { const grade=attempt.grades?.find(item => item.question_id===question.id); return <section key={question.id} className="space-y-2 border-t border-border pt-4"><h3 className="text-sm font-medium">Question {index+1} · {question.marks} marks</h3><MarkdownContent content={question.prompt} />
      {editable && !!question.options?.length && attempt.extraction && <p className="text-sm text-muted">Answer text to review: {answers[question.id] || 'Not answered'}</p>}
      {editable && question.options?.length ? <ChoiceOptions kind="single_choice" question={`Answer ${index+1}`} hideLegend options={question.options} selected={answers[question.id] ? [answers[question.id]] : []} disabled={busy} onChange={selected => { setAnswers(previous => ({ ...previous, [question.id]:selected[0] })); operation.current=crypto.randomUUID(); setConfirmed(false); }} /> : editable ? <textarea aria-label={`Answer ${index+1}`} className="min-h-28 w-full rounded-xl border border-border-strong bg-input p-3 text-sm text-foreground focus-visible:ring-2 focus-visible:ring-accent" maxLength={8000} disabled={busy} value={answers[question.id] ?? ''} onChange={event => { setAnswers(previous => ({ ...previous, [question.id]:event.target.value })); operation.current=crypto.randomUUID(); setConfirmed(false); }} /> : <MarkdownContent content={question.options?.find(option => option.id===attempt.answers[question.id])?.label ?? attempt.answers[question.id] ?? ''} />}
      {grade && <div className="space-y-1 text-sm"><p className="font-medium">{grade.score}/{question.marks} · Grade confidence {Math.round(grade.confidence*100)}%</p><MarkdownContent content={grade.feedback} />{grade.misconceptions.map((value,i) => <p key={i} className="text-muted">{value}</p>)}</div>}
    </section>; })}
    {editable && <><Select aria-label="Assistance used" disabled={busy} value={assistance} onChange={event => { setAssistance(event.target.value as typeof assistance); operation.current=crypto.randomUUID(); }}><option value="unknown">Assistance not specified</option><option value="independent">I answered independently</option><option value="assisted">I used hints or assistance</option></Select>{attempt.extraction && <Toggle label="I reviewed and corrected all extracted answers" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />}<Button disabled={busy || assessment.questions.some(question => !answers[question.id]?.trim()) || !!attempt.extraction && !confirmed} loading={busy} onClick={() => void submit()}>{attempt.extraction ? 'Confirm text & submit' : 'Submit answers'}</Button></>}
    {['submitted','grading'].includes(attempt.state) && <p role="status" className="text-sm text-muted">Grading your answers…</p>}
    {attempt.error && <p role="alert" className="text-sm text-danger">Your answers could not be evaluated.</p>}
    {attempt.state==='graded' && <><p role="status" className="text-sm text-muted">{attempt.evidence_status==='applied' ? 'Feedback saved and learner evidence applied.' : attempt.evidence_status==='partial' ? 'Feedback saved. Learner evidence was updated for confidently graded answers.' : 'Feedback saved. The grade was too uncertain to update learner evidence.'}</p>{!correcting && <Button variant="secondary" onClick={() => { setCorrecting(true); setAnswers(attempt.answers); setAssistance(attempt.assistance ?? 'unknown'); setConfirmed(false); operation.current=crypto.randomUUID(); }}>Correct answers or transcription</Button>}</>}
    {!!attempt.grade_history.length && <details className="text-sm"><summary className="cursor-pointer">Previous grade revisions</summary>{attempt.grade_history.map(history => <div key={history.grade_revision} className="space-y-2 py-3"><p className="font-medium">Revision {history.grade_revision}</p>{history.grades.map(grade => <p key={grade.question_id}>{grade.score} marks · {grade.feedback}</p>)}</div>)}</details>}
  </section>;
}
