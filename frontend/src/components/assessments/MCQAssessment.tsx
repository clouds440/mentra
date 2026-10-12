import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { Button, Select } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { ApiError } from '../../services/api';
import { assessments } from '../../services/assessments';
import type { Assessment, AssessmentAttempt } from '../../types/assessments';
import { AnswerSheet } from './AssessmentWorkspace';
import { useAuth } from '../auth/AuthProvider';
import { assessmentSession } from '../../stores/assessmentSession';
import { QuizAnswerReview } from './QuizAnswerReview';
import { LoaderCircle } from 'lucide-react';

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
    return q.options?.some(option => option.id === answer) ? [[q.id, answer]] : [];
  })));
  const [index, setIndex] = useState(() => Math.min(assessment.questions.length - 1, restored?.index ?? Math.max(0, assessment.questions.findIndex(q => !answers[q.id]))));
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
  const answered = assessment.questions.filter(q => !!answers[q.id]).length;
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
    <p role="status" className="text-sm text-muted">Question {index+1} of {assessment.questions.length} · {answered} answers selected</p>
    <div role="progressbar" aria-label="Quiz progress" aria-valuemin={0} aria-valuemax={assessment.questions.length} aria-valuenow={answered} className="h-2 overflow-hidden rounded-full bg-border">
      <div className="h-full rounded-full bg-accent" style={{ width: `${answered / assessment.questions.length * 100}%` }} />
    </div>
    <MarkdownContent content={question.prompt} />
    <ChoiceOptions kind="single_choice" question={`Answer question ${index+1}`} hideLegend options={question.options ?? []}
      selected={answers[question.id] ? [answers[question.id]] : []} disabled={disabled || busy} renderLabel={label => <MarkdownContent content={label} />}
      onChange={selected => { setAnswers(previous => ({ ...previous, [question.id]: selected[0] })); operation.current=crypto.randomUUID(); }} />
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {finalQuestion && <><p className="text-sm text-muted">Review with Back. All answers are sent together when you submit.</p><Select aria-label="Quiz assistance used" disabled={disabled || busy} value={assistance} onChange={event => { setAssistance(event.target.value as typeof assistance); operation.current=crypto.randomUUID(); }}><option value="unknown">Assistance not specified</option><option value="independent">I answered independently</option><option value="assisted">I used hints or assistance</option></Select></>}
    <div className="flex flex-wrap items-center gap-2"><Button size="sm" variant="secondary" disabled={disabled || busy || index===0} onClick={() => setIndex(value => value-1)}>Back</Button><Button size="sm" disabled={disabled || busy || (finalQuestion ? answered !== assessment.questions.length : !answers[question.id])} loading={busy} onClick={() => finalQuestion ? void submit() : setIndex(value => value+1)}>{finalQuestion ? 'Submit' : 'Next'}</Button>{actions}</div>
  </section>;
}
