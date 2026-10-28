import { AssistanceSelector } from './AssistanceSelector';
import { AnswerSheetUpload } from './AnswerSheetUpload';
import { PrintPaperButton } from './PrintPaperButton';
import { MistakesPractice } from './MistakesPractice';
import { AttemptBadges } from './AttemptBadges';
import { buttonStyles } from '../ui/Button';
import { Tabs } from '../ui/Tabs';
import { ClipboardCheck, Plus, ArrowUpRight, Sparkles, LoaderCircle } from 'lucide-react';
import { WorkspaceHeader, WorkspaceEmpty } from '../workspace/WorkspaceHeader';
import { materialWarningMessage } from '../../services/userError';
import { usePageRefresh, refreshPage } from '../../hooks/usePageRefresh';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { AssessmentFeedback } from './AssessmentFeedback';
import { AssessmentPaper, PaperHeader, PracticeNotice, questionLabel, selectedIds, selectedAnswer, showsAssessmentMarks } from './AssessmentPaper';
import { MCQAssessment } from './MCQAssessment';
import { usesInteractiveAssessment } from './assessmentDelivery';
import { AssessmentGenerationCard } from './AssessmentGenerationCard';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { Toggle } from '../ui/Toggle';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button, Textarea } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { AnswerContent } from '../content/AnswerContent';
import { assessments } from '../../services/assessments';
import { practiceDraft } from '../../services/practiceIntent';
import { restoreAssessmentTargets, rememberAssessmentTargets } from '../../services/assessmentTargetDraft';
import { AssessmentCreateForm } from './AssessmentCreateForm';
import type { Assessment, AssessmentListItem, AssessmentAttempt, AssessmentGeneration } from '../../types/assessments';
import type { LearningContext } from '../../types/rag';
import { assessmentSession, useEvaluatedAttempt } from '../../stores/assessmentSession';
import { QuizAnswerReview } from './QuizAnswerReview';

export function AssessmentWorkspace() { const { identity } = useAuth(); return <Workspace key={identity?.learner_id} owner={identity?.learner_id ?? ''} />; }
function Workspace({owner}: {owner:string}) {
  const [params, setParams] = useSearchParams();
  const id = params.get('assessment');
  const attemptId = params.get('attempt');
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<AssessmentListItem[]>([]);
  const [contexts, setContexts] = useState<LearningContext[]>([]);
  const [current, setCurrent] = useState<Assessment | null>(null);
  const [attempts, setAttempts] = useState<AssessmentAttempt[]>([]);
  const [attempt, setAttempt] = useState<AssessmentAttempt | null>(null);
  const tab = params.get('tab') === 'mistakes' ? 'mistakes' : params.get('tab') === 'create' ? 'create' : 'assessments';
  function changeTab(value: 'create' | 'assessments' | 'mistakes') {
    const next = new URLSearchParams(params);
    if (value !== 'assessments') next.set('tab', value); else next.delete('tab');
    setParams(next);
  }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [more, setMore] = useState<number | null>(null);
  const [draft, setDraft] = useState<AssessmentGeneration>(() => restoreAssessmentTargets(owner, practiceDraft(params),
    params.has('concept') || params.has('document') || params.has('learning_topic') || params.has('topic') || params.has('context')));
  useEffect(() => { rememberAssessmentTargets(owner, draft); }, [owner, draft.topic_id, draft.context_id, draft.topic, draft.concept_ids]);
  const intentKey = JSON.stringify([params.get('context'), params.get('topic'), params.get('learning_topic'), params.get('purpose'), params.getAll('concept'), params.getAll('document')]);
  const previousIntent = useRef(intentKey);
  useEffect(() => {
    if (previousIntent.current === intentKey) return;
    previousIntent.current = intentKey;
    if (params.has('concept') || params.has('document') || params.has('learning_topic')) { setDraft(practiceDraft(params)); }
  }, [intentKey]);
  const active = useRef<AbortController | null>(null);
  const startOperation = useRef(crypto.randomUUID());
  const generating = useRef(false);
  const generationOperation = useRef<{ payload: string; id: string }>();
  usePageRefresh(() => setReload(value => value + 1), !busy && !attempt, ['assessments']);
  useEffect(() => {
    if (tab === 'mistakes') { setLoading(false); return; }
    const controller = new AbortController(); setLoading(items.length === 0 || !!id && current?.id !== id); setError(''); if (current?.id !== id) { setCurrent(null); setAttempt(null); }
    void assessments.page(controller.signal, tab, id).then(page => {
      const history = page.attempts;
      if (!controller.signal.aborted) { if (tab === 'assessments') { setItems(page.items); setMore(page.next_offset); } if (tab === 'create') setContexts(page.contexts); setCurrent(page.detail); setAttempts(history); if (attemptId) setAttempt(history.find(item => item.id === attemptId) ?? null); else setAttempt(history.find(item => item.state !== 'draft' || Object.keys(item.answers).length > 0) ?? history[0] ?? null); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load assessments.'); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); active.current?.abort(); };
  }, [id, attemptId, reload, tab]);
  function updateAttempt(result: AssessmentAttempt) {
    setAttempt(result);
    setAttempts(previous => [result, ...previous.filter(item => item.id !== result.id)]);
    setItems(previous => previous.map(item => {
      if (item.id !== result.assessment_id) return item;
      const summary = { count: Math.max(item.attempt_summary?.count ?? 0, result.attempt_number), latest_state: result.attempt_number >= (item.attempt_summary?.count ?? 0) ? result.state : item.attempt_summary?.latest_state ?? result.state,
        graded_attempt_id: item.attempt_summary?.graded_attempt_id ?? null, graded_attempt_number: item.attempt_summary?.graded_attempt_number ?? 0, correct: item.attempt_summary?.correct ?? 0,
        incorrect: item.attempt_summary?.incorrect ?? 0, partial: item.attempt_summary?.partial ?? 0 };
      if (result.state === 'graded' && result.attempt_number >= summary.graded_attempt_number) {
        summary.graded_attempt_id = result.id; summary.graded_attempt_number = result.attempt_number; summary.correct = 0; summary.incorrect = 0; summary.partial = 0;
        for (const question of current?.id === item.id ? current.questions : []) {
          const grade = result.grades?.find(value => value.question_id === question.id);
          if (!grade) continue;
          if (grade.score >= question.marks) summary.correct++;
          else { summary.incorrect++; if (grade.score > 0) summary.partial++; }
        }
      }
      return {...item, attempt_summary: summary};
    }));
  }
  async function generate() {
    if (generating.current) return;
    generating.current = true;
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try {
      const { client_request_id: initialId, ...payload } = { ...draft, count: draft.count ?? 5, grounded: draft.document_ids.length > 0 };
      const fingerprint = JSON.stringify(payload);
      if (generationOperation.current?.payload !== fingerprint) generationOperation.current = { payload: fingerprint, id: generationOperation.current ? crypto.randomUUID() : initialId };
      const request = { ...payload, client_request_id: generationOperation.current.id };
      const value = await assessments.queue(request, controller.signal);
      if (!controller.signal.aborted) { setParams({ tab: 'create', generation: value.id }); generationOperation.current = undefined; setDraft(previous => ({ ...previous, client_request_id: crypto.randomUUID() })); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to generate assessment.'); }
    finally { generating.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  async function start() {
    if (!current) return;
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try { const result = await assessments.start(current.id, startOperation.current, controller.signal); if (!controller.signal.aborted) { updateAttempt(result); startOperation.current = crypto.randomUUID(); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to start attempt.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function loadMore() {
    if (more === null) return; const controller = new AbortController(); active.current = controller;
    try { const result = await assessments.page(controller.signal, 'assessments', undefined, more); if (!controller.signal.aborted) { setItems(previous => [...previous, ...result.items]); setMore(result.next_offset); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load more assessments.'); }
  }
  return <div className="h-full overflow-y-auto"><div className="page-container">
    <WorkspaceHeader title={tab === 'create' ? 'Create assessment' : 'Assessments'} description={tab === 'create' ? 'Choose a topic and the practice you want. Mentra handles the rest.' : 'Turn what you’re learning into practice. Explore your questions, continue an attempt or start something new.'} icon={ClipboardCheck} actions={tab !== 'create' && <Button disabled={busy} onClick={() => changeTab('create')}><Plus size={16} aria-hidden="true" />New assessment</Button>} />
    <Tabs label="Assessment sections" value={tab} onChange={changeTab} options={(['assessments', 'mistakes', 'create'] as const).map(value => ({ value, label: value === 'create' ? 'Create new' : value === 'mistakes' ? 'Practice my mistakes' : 'Assessments', id: `assessment-tab-${value}`, panel: `assessment-panel-${value}`, disabled: busy }))} />
    {error && <p role="alert" className="text-sm text-danger">{error} <button type="button" className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'ml-2 mt-1' })} onClick={() => refreshPage(() => setReload(value => value + 1))}>Refresh</button></p>}
    <section role="tabpanel" id="assessment-panel-mistakes" aria-labelledby="assessment-tab-mistakes" hidden={tab !== 'mistakes'}>{tab === 'mistakes' && <MistakesPractice />}</section>
    <section role="tabpanel" id="assessment-panel-create" aria-labelledby="assessment-tab-create" hidden={tab !== 'create'}>
    {params.get('generation') && <AssessmentGenerationCard key={params.get('generation')!} id={params.get('generation')!} title="Your assessment" onComplete={result => setParams({ assessment: 'assessment' in result ? result.assessment.id : result.id })} />}
    {loading && !error ? <Skeleton variant="form" rows={5} /> : <AssessmentCreateForm topics={contexts.map(item => item.name)} draft={draft} onChange={setDraft} busy={busy} onSubmit={() => void generate()} />}
    </section>
    <section role="tabpanel" id="assessment-panel-assessments" aria-labelledby="assessment-tab-assessments" hidden={tab !== 'assessments'} className="space-y-5">
    {loading && !error && <Skeleton variant="card" />}
    {current && <section className="workspace-panel space-y-5"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-xl font-medium text-heading">{current.title}</h2><Button variant="secondary" disabled={busy} loading={busy} onClick={() => void start()}>Start new attempt</Button></div>
      {attempt ? usesInteractiveAssessment(current) && attempt.state === 'draft' ? <MCQAssessment key={attempt.id} assessment={current} initial={attempt} onChange={updateAttempt} /> : <AnswerSheet key={attempt.id} assessment={current} initial={attempt} onChange={updateAttempt} /> : <><AssessmentPaper assessment={current} /><AnswerSheetUpload attempt={null} onBusyChange={setBusy} disabled={busy} onStart={async signal => { const value = await assessments.start(current.id, startOperation.current, signal); if (!signal.aborted) startOperation.current=crypto.randomUUID(); return value; }} onChange={updateAttempt} /></>}
      <h3 className="font-medium">Attempt history</h3>{attempts.length === 0 && <p className="text-sm text-muted">No attempts yet.</p>}<ul className="space-y-2">{attempts.map(value => <li key={value.id}><button type="button" aria-pressed={attempt?.id === value.id} className="w-full rounded-control border border-border px-3 py-2.5 text-left text-sm text-heading transition-colors duration-150 hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent aria-pressed:border-accent aria-pressed:bg-active" onClick={() => setAttempt(value)}>Attempt {value.attempt_number} · {value.state} · {new Date(value.created_at).toLocaleString()}</button></li>)}</ul>
    </section>}
    <h2 className="text-lg font-medium">Your assessments</h2>{!loading && !error && items.length === 0 && <WorkspaceEmpty icon={Sparkles} title="Practice starts with a question" description="Create an assessment around a topic you’re learning. Your attempts and feedback stay together here." action={<Button variant="secondary" onClick={() => changeTab('create')}>Create your first assessment</Button>} />}<ul className="workspace-grid">{items.map(item => <li key={item.id}><button className="workspace-item flex h-full w-full items-start gap-3 text-left text-heading focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setParams({ assessment: item.id })}><span className="grid h-8 w-8 shrink-0 place-items-center rounded-control bg-active text-accent"><ClipboardCheck size={19} aria-hidden="true" /></span><span className="min-w-0 flex-1"><span className="block break-words font-medium">{item.title}</span><span className="mt-2 block text-xs text-muted">{item.question_count} questions{item.has_paper ? ` · ${item.part_count} parts` : ''}</span><span className="workspace-status mt-3 capitalize">{item.tags?.includes('revision assessment') ? 'Revision assessment' : item.purpose}</span><AttemptBadges summary={item.attempt_summary} /></span><ArrowUpRight size={16} className="shrink-0 text-subtle" aria-hidden="true" /></button></li>)}</ul>{more !== null && <Button variant="secondary" onClick={() => void loadMore()}>Load more</Button>}
    </section>
  </div></div>;
}

export function AnswerSheet({ assessment, initial, onChange, actions }: { assessment: Assessment; initial: AssessmentAttempt; onChange: (attempt: AssessmentAttempt) => void; actions?: ReactNode }) {
  const { identity } = useAuth();
  const owner = identity?.learner_id;
  const canonical = useEvaluatedAttempt(initial.id);
  const [attempt, setAttempt] = useState(initial);
  const [answers, setAnswers] = useState(initial.state==='pending_transcription' ? initial.extraction?.answers ?? initial.answers : initial.answers);
  const [confirmed, setConfirmed] = useState(false);
  const [assistance, setAssistance] = useState<'unknown' | 'independent' | 'assisted'>(initial.reported_assistance ?? initial.assistance ?? 'unknown');
  const [correcting, setCorrecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [activeAction, setActiveAction] = useState<'submit' | 'save' | 'retry'>();
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  const operation = useRef(crypto.randomUUID());
  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => { assessmentSession.observe(owner, attempt); }, [owner, attempt.id, attempt.state, attempt.revision, attempt.retry_pending]);
  useEffect(() => { if (canonical && canonical !== attempt && canonical.revision >= attempt.revision) { if (canonical.state === 'pending_transcription' && (attempt.state !== 'pending_transcription' || attempt.extraction !== canonical.extraction)) { setAnswers(canonical.extraction?.answers ?? canonical.answers); setConfirmed(false); } setAttempt(canonical); onChange(canonical); } }, [canonical, attempt]);
  const evaluating = ['submitted','grading'].includes(attempt.state) || attempt.state === 'failed' && !!attempt.retry_pending;
  const quizPending = evaluating && usesInteractiveAssessment(assessment);
  const editable = attempt.state === 'draft' || attempt.state === 'pending_transcription' || correcting;
  async function submit() {
    const controller = new AbortController(); active.current = controller; setBusy(true); setActiveAction('submit'); setError('');
    try { const result = await (correcting ? assessments.correct : assessments.submit)(attempt, answers, operation.current, confirmed, controller.signal, assistance); if (!controller.signal.aborted) { setAttempt(result); setCorrecting(false); onChange(result); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to submit answers.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function saveProgress() {
    if (busy || attempt.state !== 'draft') return;
    const controller = new AbortController(); active.current=controller; setBusy(true); setActiveAction('save'); setError('');
    try {
      const value = await assessments.saveDraft(attempt, Object.fromEntries(Object.entries(answers).filter(([,answer]) => answer.trim())), controller.signal, assistance);
      if (!controller.signal.aborted) { setAttempt(value); setAnswers(value.answers); onChange(value); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Could not save progress. Your answers are still here.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function retryEvaluation() {
    if (busy) return;
    const controller=new AbortController(); active.current=controller; setBusy(true); setActiveAction('retry'); setError('');
    try {
      const result=await assessments.retryEvaluation(attempt,operation.current,controller.signal);
      if(!controller.signal.aborted) { setAttempt(result); assessmentSession.observe(owner,result); onChange(result); operation.current=crypto.randomUUID(); }
    } catch(reason) { if(!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Could not retry evaluation. Your submitted answers are kept.'); }
    finally { if(!controller.signal.aborted) setBusy(false); }
  }
  return <section aria-label="Assessment answer sheet" className="space-y-5">
    <PracticeNotice assessment={assessment} />
    <PaperHeader assessment={assessment} />

    {attempt.state==='graded' && !correcting && <AssessmentFeedback assessment={assessment} attempt={attempt} />}
    {evaluating && <p role="status" className="flex items-center gap-2 text-sm text-muted"><LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />Evaluating your answers…</p>}
    <p className="text-sm text-muted">Attempt {attempt.attempt_number} · {attempt.state === 'graded' ? 'Attempted' : attempt.state}</p>{error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {editable && !correcting && <AnswerSheetUpload attempt={attempt} draftAnswers={answers} assistance={assistance} onBusyChange={setBusy} disabled={busy} onChange={result => { setAttempt(result); setAnswers(result.extraction?.answers ?? {}); setConfirmed(false); operation.current=crypto.randomUUID(); assessmentSession.observe(owner,result); onChange(result); }} />}
    {!assessment.paper && <PrintPaperButton assessment={assessment} />}
    {attempt.extraction && editable && <div className="space-y-2 text-sm text-muted"><p>{attempt.extraction.handwriting_support==='typed_chat' ? 'Your chat answers are ready. Check their question numbers before submitting.' : attempt.extraction.handwriting_support==='vision_requires_review' ? 'Image transcription is ready. Review every answer and its question number before submitting.' : 'Review and correct every extracted answer before submitting. Handwriting may not have been read accurately.'}</p>{attempt.extraction.warnings.map((warning,index) => <p key={index}>{materialWarningMessage(warning)}</p>)}</div>}
    {quizPending && <QuizAnswerReview assessment={assessment} answers={attempt.answers} />}
    {!quizPending && (attempt.state !== 'graded' || correcting) && assessment.questions.map((question,index) => { const grade=attempt.grades?.find(item => item.question_id===question.id); return <section key={question.id} className="space-y-2 border-t border-border pt-4">{question.section && question.section !== assessment.questions[index-1]?.section && <h3 className="text-sm font-semibold text-accent">{question.section}</h3>}<h3 className="text-sm font-medium">{questionLabel(question,index)}{showsAssessmentMarks(assessment) ? ` · ${question.marks} marks` : ''}</h3>{!!question.context && <div className="rounded-lg border border-border bg-surface p-3"><MarkdownContent content={question.context} /></div>}<MarkdownContent content={question.prompt} />
      {editable && !!question.options?.length && attempt.extraction && <p className="text-sm text-muted">Answer text to review: {answers[question.id] || 'Not answered'}</p>}
      {editable && question.options?.length ? <ChoiceOptions kind={question.answer_mode === 'multiple_choice' ? 'multiple_choice' : 'single_choice'} question={`Answer ${questionLabel(question,index).replace('Question ', '')}`} hideLegend options={question.options} selected={selectedIds(question, answers[question.id])} renderLabel={label => <MarkdownContent content={label} />} disabled={busy} onChange={selected => { setAnswers(previous => ({ ...previous, [question.id]: question.answer_mode === 'multiple_choice' ? selected.length ? JSON.stringify(selected) : '' : selected[0] })); operation.current=crypto.randomUUID(); setConfirmed(false); }} /> : editable ? <Textarea aria-label={`Answer ${questionLabel(question,index).replace('Question ', '')}`} className="min-h-28 w-full rounded-xl border border-border-strong bg-input p-3 text-sm text-foreground focus-visible:ring-2 focus-visible:ring-accent"  disabled={busy} value={answers[question.id] ?? ''} onChange={event => { setAnswers(previous => ({ ...previous, [question.id]:event.target.value })); operation.current=crypto.randomUUID(); setConfirmed(false); }} /> : <AnswerContent content={selectedAnswer(question, attempt.answers[question.id])} />}
      {grade && <div className="space-y-1 text-sm"><p className="font-medium">{showsAssessmentMarks(assessment) ? `${grade.score}/${question.marks} · ` : ''}Review confidence {Math.round(grade.confidence*100)}%</p><MarkdownContent content={grade.feedback} />{grade.misconceptions.map((value,i) => <p key={i} className="text-muted">{value}</p>)}</div>}
    </section>; })}
    {editable && <>{assessment.practice_source && <p className="text-xs text-muted">Earlier feedback is available, so this attempt is recorded as repeated practice.</p>}<AssistanceSelector disabled={busy} value={assistance} onChange={value => { setAssistance(value); operation.current=crypto.randomUUID(); }} />{attempt.extraction && <Toggle label="I reviewed and corrected all extracted answers" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />}</>}
    {attempt.error && !evaluating && <p role="alert" className="text-sm text-danger">{attempt.error} Your answers are saved.</p>}
    {attempt.state==='graded' && <><p role="status" className="text-sm text-muted">{attempt.evidence_status==='pending' ? 'Results saved. Learning progress updates in the background.' : attempt.evidence_status==='applied' ? 'Feedback saved and learning progress updated.' : attempt.evidence_status==='partial' ? 'Feedback saved. Learning progress was updated where the review was confident.' : 'Feedback saved. Learning progress could not be updated for this review.'}</p></>}
    {!!attempt.grade_history.length && <details className="text-sm"><summary className="ui-disclosure cursor-pointer">Previous grade revisions</summary>{attempt.grade_history.map(history => <div key={history.grade_revision} className="space-y-2 py-3"><p className="font-medium">Revision {history.grade_revision}</p>{history.grades.map(grade => <p key={grade.question_id}>{showsAssessmentMarks(assessment) ? `${grade.score} marks · ` : ''}{grade.feedback}</p>)}</div>)}</details>}
    <div className="flex flex-wrap items-center gap-2">
      {attempt.state==='failed' && !attempt.retry_pending && <Button size="sm" loading={busy && activeAction==='retry'} disabled={busy} onClick={() => void retryEvaluation()}>Retry evaluation</Button>}
      {editable && !correcting && attempt.state === 'draft' && <Button size="sm" variant="secondary" disabled={busy} loading={busy && activeAction === 'save'} onClick={() => void saveProgress()}>Save progress</Button>}
      {editable && <Button size="sm" disabled={busy || assessment.questions.some(question => !answers[question.id]?.trim()) || !!attempt.extraction && !confirmed} loading={busy && activeAction === 'submit'} onClick={() => void submit()}>{attempt.extraction ? 'Confirm text & submit' : 'Submit answers'}</Button>}
      {attempt.state === 'graded' && !correcting && <Button size="sm" variant="secondary" onClick={() => { setCorrecting(true); setAnswers(attempt.answers); setAssistance(attempt.reported_assistance ?? attempt.assistance ?? 'unknown'); setConfirmed(false); operation.current=crypto.randomUUID(); }}>Correct answers or transcription</Button>}
      {actions}
    </div>
  </section>;
}
