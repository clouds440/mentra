import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { Button, Select, Textarea } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { ApiError } from '../../services/api';
import { assessments } from '../../services/assessments';
import type { Assessment, AssessmentAttempt } from '../../types/assessments';
import { AnswerSheet } from './AssessmentWorkspace';
import { useAuth } from '../auth/AuthProvider';
import { assessmentSession } from '../../stores/assessmentSession';
import { QuizAnswerReview } from './QuizAnswerReview';
import { ArrowLeft, ArrowRight, Check, LoaderCircle, Sparkles } from 'lucide-react';
import { questionKind, selectedIds, showsAssessmentMarks, PracticeNotice } from './AssessmentPaper';
import { useQuestionNavigation } from './useQuestionNavigation';

export function MCQAssessment({ assessment, initial, onChange, onStart, disabled = false, actions }: { assessment: Assessment; initial: AssessmentAttempt | null; onChange: (value: AssessmentAttempt) => void; onStart?: (signal: AbortSignal) => Promise<AssessmentAttempt>; disabled?: boolean; actions?: ReactNode }) {
  const { identity } = useAuth();
  const owner = identity?.learner_id;
  const signature = JSON.stringify([assessment.revision, assessment.questions.map(q => [q.id, q.options?.map(option => option.id)])]);
  const key = (id?: string) => `${assessment.id}:${id ?? 'new'}`;
  const [restored] = useState(() => {
    if (initial && initial.state !== 'draft') return undefined;
    const stored = assessmentSession.draft(owner, key(initial?.id)) ?? (initial ? assessmentSession.draft(owner, key()) : undefined);
    return stored?.signature === signature ? stored : undefined;
  });
  const [attempt, setAttempt] = useState(restored?.attempt ?? initial);
  const [answers, setAnswers] = useState(() => Object.fromEntries(assessment.questions.flatMap(q => {
    const answer = (restored?.answers ?? initial?.answers ?? {})[q.id];
    return answer && (q.options?.length ? selectedIds(q, answer).length > 0 && selectedIds(q, answer).every(id => q.options!.some(option => option.id === id)) : true) ? [[q.id, answer]] : [];
  })));
  const { index, setIndex, direction } = useQuestionNavigation(() => Math.min(assessment.questions.length - 1, restored?.index ?? Math.max(0, assessment.questions.findIndex(q => !answers[q.id]))));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [assistance, setAssistance] = useState<'unknown' | 'independent' | 'assisted'>(restored?.assistance ?? initial?.assistance ?? 'unknown');
  const active = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const operation = useRef(restored?.operation ?? crypto.randomUUID());
  const draftKey = useRef(key(initial?.id));
  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => {
    const nextKey = key(attempt?.id);
    if (draftKey.current !== nextKey) assessmentSession.forget(owner, draftKey.current);
    draftKey.current = nextKey;
    if (attempt && attempt.state !== 'draft') { assessmentSession.forget(owner, nextKey); return; }
    assessmentSession.remember(owner, nextKey, { signature, answers, index, assistance, operation: operation.current, attempt });
  }, [owner, assessment.id, signature, answers, index, assistance, attempt]);
  const question = assessment.questions[index];
  const answered = assessment.questions.filter(q => !!answers[q.id]?.trim()).length;
  const finalQuestion = index === assessment.questions.length - 1;
  async function submit() {
    if (lock.current || disabled || answered !== assessment.questions.length) return;
    lock.current = true; setBusy(true); setError('');
    const controller = new AbortController(); active.current = controller;
    const submission = operation.current;
    assessmentSession.begin(owner, submission);
    let working = attempt;
    try {
      if (!working) {
        if (!onStart) throw new Error('Unable to start this quiz. Reload and try again.');
        working = await onStart(controller.signal);
        if (controller.signal.aborted) return;
        setAttempt(working);
      }
      const result = await assessments.submit(working, answers, submission, false, controller.signal, assistance);
      if (!controller.signal.aborted) { setAttempt(result); assessmentSession.observe(owner, result); onChange(result); }
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof ApiError ? reason.message : 'Unable to submit your quiz. Your choices are kept; try again.');
        // Recover the authoritative revision after an interrupted write.
        try { if (working) { const result = await assessments.attempt(working.id, controller.signal); if (!controller.signal.aborted) { setAttempt(result); assessmentSession.observe(owner, result); if (reason instanceof ApiError && reason.status === 409 && result.state === 'draft') setError('This attempt changed elsewhere. Your choices are kept locally; review them before submitting again.'); if (result.state !== 'draft') onChange(result); } } } catch { /* Keep choices and submission ID for retry. */ }
      }
    } finally { assessmentSession.end(owner, submission); lock.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  if (busy) return <section className="space-y-4"><p role="status" className="flex items-center gap-2 text-sm text-muted"><LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />Submitting your answers…</p><QuizAnswerReview assessment={assessment} answers={answers} /></section>;
  if (attempt && attempt.state !== 'draft') return <AnswerSheet assessment={assessment} initial={attempt} onChange={onChange} actions={actions} />;
  return <section aria-label="Interactive quiz" className="space-y-4">
    <PracticeNotice assessment={assessment} />
    <div className="flex flex-wrap items-center justify-between gap-2"><p role="status" className="text-xs font-medium text-muted">Question {index+1} of {assessment.questions.length} · {answered} answered</p><span className="flex items-center gap-1 text-[11px] font-medium text-accent"><Sparkles size={12} aria-hidden="true" />Practice at your pace</span></div>
    <div role="progressbar" aria-label="Quiz progress" aria-valuemin={0} aria-valuemax={assessment.questions.length} aria-valuenow={answered} className="h-2 overflow-hidden rounded-full bg-border">
      <div className="h-full rounded-full bg-accent" style={{ width: `${answered / assessment.questions.length * 100}%` }} />
    </div>
    <nav aria-label="Quiz questions" className="flex flex-wrap gap-1.5">{assessment.questions.map((q, i) => <button key={q.id} type="button" aria-label={`Go to question ${i+1}${answers[q.id]?.trim() ? ', answered' : ''}`} aria-current={index === i ? 'step' : undefined} disabled={disabled || busy} onClick={() => setIndex(i)} className={`grid h-8 min-w-8 place-items-center rounded-md border px-1 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-accent ${index === i ? 'border-accent bg-accent/10 text-accent' : answers[q.id]?.trim() ? 'border-border-strong bg-active text-heading' : 'border-border text-muted hover:bg-hover'}`}>{answers[q.id]?.trim() && index !== i ? <Check size={13} aria-hidden="true" /> : i+1}</button>)}</nav>
    <div key={question.id} data-navigation={direction} className="question-transition quiz-question space-y-4 rounded-lg border border-border-strong bg-surface p-3 sm:p-4">
    <div className="flex items-center justify-between gap-2 text-[11px]"><span className="font-medium uppercase tracking-wider text-accent">{questionKind(question)}</span>{showsAssessmentMarks(assessment) && <span className="tabular-nums text-muted">{question.marks} {question.marks === 1 ? 'mark' : 'marks'}</span>}</div>
    <MarkdownContent content={question.prompt} />
    {question.context && <div className="border-l-2 border-accent/30 pl-3 text-sm text-muted"><MarkdownContent content={question.context} /></div>}
    {question.options?.length ? <ChoiceOptions kind={question.answer_mode === 'multiple_choice' ? 'multiple_choice' : 'single_choice'} question={`Answer question ${index+1}`} hideLegend options={question.options}
      selected={selectedIds(question, answers[question.id])} disabled={disabled || busy} renderLabel={label => <MarkdownContent content={label} />}
      onChange={selected => { setAnswers(previous => ({ ...previous, [question.id]: question.answer_mode === 'multiple_choice' ? selected.length ? JSON.stringify(selected) : '' : selected[0] })); operation.current=crypto.randomUUID(); }} /> : <div className="space-y-1.5"><label htmlFor={`quiz-answer-${question.id}`} className="text-xs font-medium text-muted">Your answer</label><Textarea id={`quiz-answer-${question.id}`} aria-label={`Answer question ${index+1}`} rows={question.question_type === 'short_answer' ? 3 : 5}  disabled={disabled || busy} value={answers[question.id] ?? ''} placeholder="Write your answer in your own words…" onChange={event => { setAnswers(previous => ({ ...previous, [question.id]: event.target.value })); operation.current=crypto.randomUUID(); }} /><p className="text-[11px] text-subtle">{question.question_type === 'short_answer' ? 'A few words or a short explanation is enough.' : 'Include your reasoning or working where it helps.'}</p></div>}
    </div>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {finalQuestion && <><p className="text-sm text-muted">Review with Back. All answers are sent together when you submit.</p>{assessment.practice_source ? <p className="text-xs text-muted">Earlier feedback is available, so this attempt is recorded as repeated practice.</p> : <Select aria-label="Quiz assistance used" disabled={disabled || busy} value={assistance} onChange={event => { setAssistance(event.target.value as typeof assistance); operation.current=crypto.randomUUID(); }}><option value="unknown">Assistance not specified</option><option value="independent">I answered independently</option><option value="assisted">I used hints or assistance</option></Select>}</>}
    <div className="flex flex-wrap items-center gap-2"><Button size="sm" variant="secondary" disabled={disabled || busy || index===0} onClick={() => setIndex(value => value-1)}><ArrowLeft size={13} aria-hidden="true" />Back</Button><Button size="sm" disabled={disabled || busy || (finalQuestion ? answered !== assessment.questions.length : !answers[question.id]?.trim())} loading={busy} onClick={() => finalQuestion ? void submit() : setIndex(value => value+1)}>{finalQuestion ? 'Submit' : 'Next'}{!finalQuestion && <ArrowRight size={13} aria-hidden="true" />}</Button>{actions}</div>
  </section>;
}
