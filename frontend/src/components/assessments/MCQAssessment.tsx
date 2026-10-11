import { useEffect, useRef, useState } from 'react';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { Button, Select } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { ApiError } from '../../services/api';
import { assessments } from '../../services/assessments';
import type { Assessment, AssessmentAttempt } from '../../types/assessments';
import { AnswerSheet } from './AssessmentWorkspace';

export function MCQAssessment({ assessment, initial, onChange, onStart, disabled = false }: { assessment: Assessment; initial: AssessmentAttempt | null; onChange: (value: AssessmentAttempt) => void; onStart?: (signal: AbortSignal) => Promise<AssessmentAttempt>; disabled?: boolean }) {
  const [attempt, setAttempt] = useState(initial);
  const [index, setIndex] = useState(() => Math.max(0, assessment.questions.findIndex(q => !(initial?.answers ?? {})[q.id])));
  const [answers, setAnswers] = useState((initial?.answers ?? {}));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [assistance, setAssistance] = useState<'unknown' | 'independent' | 'assisted'>('unknown');
  const active = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const operation = useRef(crypto.randomUUID());
  useEffect(() => () => active.current?.abort(), []);
  const question = assessment.questions[index];
  async function save(finish: boolean) {
    if (lock.current || disabled) return;
    lock.current = true; setBusy(true); setError('');
    const controller = new AbortController(); active.current = controller;
    let working = attempt;
    try {
      if (!working) {
        if (!onStart) throw new Error('Unable to start this quiz. Reload and try again.');
        working = await onStart(controller.signal);
      }
      const result = finish ? await assessments.submit(working, answers, operation.current, false, controller.signal, assistance) : await assessments.saveDraft(working, answers, controller.signal);
      if (!controller.signal.aborted) { setAttempt(result); onChange(result); if (!finish) setIndex(value => Math.min(value+1, assessment.questions.length-1)); }
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : 'Unable to save answer. Retry or reload.');
        // Recover the authoritative revision after an interrupted write.
        try { if (working) { const result = await assessments.attempt(working.id, controller.signal); if (!controller.signal.aborted) { setAttempt(result); if (reason instanceof ApiError && reason.status === 409) { setAnswers(result.answers); setError('Answers changed elsewhere. The saved answers have been restored; review them before continuing.'); } if (result.state !== 'draft') onChange(result); } } } catch { /* Keep choices for retry. */ }
      }
    } finally { lock.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  if (attempt && attempt.state !== 'draft') return <AnswerSheet assessment={assessment} initial={attempt} onChange={onChange} />;
  return <section aria-label="Interactive quiz" className="space-y-4">
    <p role="status" className="text-sm text-muted">Question {index+1} of {assessment.questions.length} · {Object.keys(attempt?.answers ?? {}).length} answers saved</p>
    <div role="progressbar" aria-label="Quiz progress" aria-valuemin={0} aria-valuemax={assessment.questions.length} aria-valuenow={Object.keys(attempt?.answers ?? {}).length} className="h-2 overflow-hidden rounded-full bg-border">
      <div className="h-full rounded-full bg-accent" style={{ width: `${Object.keys(attempt?.answers ?? {}).length / assessment.questions.length * 100}%` }} />
    </div>
    <MarkdownContent content={question.prompt} />
    <ChoiceOptions kind="single_choice" question={`Answer question ${index+1}`} hideLegend options={question.options ?? []}
      selected={answers[question.id] ? [answers[question.id]] : []} disabled={disabled || busy}
      onChange={selected => { setAnswers(previous => ({ ...previous, [question.id]: selected[0] })); operation.current=crypto.randomUUID(); }} />
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={disabled || busy || index===0} onClick={() => setIndex(value => value-1)}>Back</Button><Button disabled={disabled || busy || !answers[question.id]} onClick={() => void save(false)}>{busy ? 'Saving…' : index < assessment.questions.length-1 ? 'Save & next' : 'Save answer'}</Button></div>
    {index===assessment.questions.length-1 && <><p className="text-sm text-muted">Review your answers with Back. Feedback appears after final submission.</p><Select aria-label="Quiz assistance used" disabled={disabled || busy} value={assistance} onChange={event => { setAssistance(event.target.value as typeof assistance); operation.current=crypto.randomUUID(); }}><option value="unknown">Assistance not specified</option><option value="independent">I answered independently</option><option value="assisted">I used hints or assistance</option></Select><Button disabled={disabled || busy || assessment.questions.some(q => !answers[q.id])} onClick={() => void save(true)}>Finish quiz</Button></>}
  </section>;
}
