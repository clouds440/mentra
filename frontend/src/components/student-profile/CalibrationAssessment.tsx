import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check } from 'lucide-react';
import { Button, Spinner } from '../ui';
import type { CalibrationAttempt, StudentProfile } from '../../types/studentProfile';
import { completeCalibration, getCalibration, profileError } from '../../services/studentProfile';

export function CalibrationAssessment({ initialAttempt, onComplete, onSkip, skipping = false }: {
  initialAttempt: CalibrationAttempt;
  onComplete: (profile: StudentProfile) => void;
  onSkip: () => void;
  skipping?: boolean;
}) {
  const [attempt, setAttempt] = useState(initialAttempt);
  const [choices, setChoices] = useState(initialAttempt.answers);
  const [index, setIndex] = useState(() => {
    const unanswered = initialAttempt.questions.findIndex((question) => !initialAttempt.answers[question.id]);
    return unanswered < 0 ? initialAttempt.questions.length - 1 : unanswered;
  });
  const [pending, setPending] = useState<'finish' | 'reload' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const question = attempt.questions[index];
  const disabled = Boolean(pending) || skipping;
  useEffect(() => {
    const current = heading.current;
    current?.focus({ preventScroll: true });
    if (current && (current.getBoundingClientRect().top < 0 || current.getBoundingClientRect().bottom > window.innerHeight)) {
      current.scrollIntoView({ block: 'nearest' });
    }
  }, [question.id]);
  async function advance() {
    const optionId = choices[question.id];
    if (busy.current || skipping || !optionId) return;
    if (index < attempt.questions.length - 1) { setIndex((value) => value + 1); return; }
    busy.current = true; setPending('finish'); setError(null);
    try {
      onComplete((await completeCalibration(attempt, choices)).profile);
    }
    catch (failure) { setError(profileError(failure)); }
    finally { busy.current = false; setPending(null); }
  }
  async function reload() {
    if (busy.current || skipping) return;
    busy.current = true; setPending('reload');
    try {
      const current = await getCalibration();
      if (current?.status === 'in_progress') { setAttempt(current); setError(null); }
      else window.location.reload();
    } catch (failure) { setError(profileError(failure)); }
    finally { busy.current = false; setPending(null); }
  }
  const last = index === attempt.questions.length - 1;
  return <section aria-label="Calibration assessment" aria-busy={disabled}>
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted">
      <p aria-live="polite">Question {index + 1} of {attempt.questions.length}</p><span>About 1–2 minutes</span>
    </div>
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-border" role="progressbar" aria-label="Assessment progress"
      aria-valuemin={0} aria-valuemax={attempt.questions.length} aria-valuenow={index + 1}>
      <div className="h-full rounded-full bg-accent transition-[width] duration-200" style={{ width: `${(index + 1) / attempt.questions.length * 100}%` }} />
    </div>
    <div key={question.id} className="auth-enter mt-7">
      <h2 ref={heading} tabIndex={-1} className="text-lg font-medium leading-7 tracking-tight text-heading outline-none">{question.prompt}</h2>
      <p className="mt-2 text-xs leading-5 text-subtle">Choose one answer. Your answers are submitted together when you finish.</p>
      <fieldset disabled={disabled} aria-label="Answer choices" className="mt-5 min-w-0 space-y-3">
        {question.options.map((option) => <label key={option.id} className="relative block cursor-pointer">
          <input type="radio" name={question.id} value={option.id} checked={choices[question.id] === option.id}
            className="peer sr-only" onChange={() => { setChoices((current) => ({ ...current, [question.id]: option.id })); }} />
          <span className="flex min-h-12 items-center justify-between gap-3 rounded-xl border border-border-strong bg-input px-4 py-3 text-sm leading-6 text-body transition-colors hover:bg-hover peer-checked:border-accent peer-checked:bg-active peer-checked:text-heading peer-focus-visible:ring-2 peer-focus-visible:ring-accent/40 peer-disabled:cursor-wait peer-disabled:opacity-70">
            <span className="min-w-0 break-words">{option.text}</span><Check aria-hidden="true" className={`shrink-0 text-accent ${choices[question.id] === option.id ? 'visible' : 'invisible'}`} size={17} /></span>
        </label>)}
      </fieldset>
    </div>
    {error && <div className="mt-5" role="alert"><p className="text-sm leading-6 text-danger">{error}</p>
      <Button className="mt-3" size="sm" variant="secondary" disabled={disabled} onClick={() => { void reload(); }}>Reload assessment</Button></div>}
    <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
      <Button variant="ghost" disabled={disabled || index === 0} onClick={() => setIndex((value) => value - 1)}>
        <ArrowLeft aria-hidden="true" size={16} />Back</Button>
      <Button disabled={disabled || !choices[question.id] || Boolean(last && attempt.questions.some((item) => !choices[item.id]))}
        onClick={() => { void advance(); }}>
        {pending === 'finish' ? 'Reading your results…' : last ? 'Finish calibration' : 'Next'}
        {pending ? <Spinner className="h-4 w-4 shrink-0" label={pending === 'finish' ? 'Submitting your assessment' : 'Restoring your assessment'} /> : <ArrowRight aria-hidden="true" className="shrink-0" size={16} />}</Button>
    </div>
    {pending === 'finish' && <p className="mt-4 text-center text-xs leading-5 text-muted" aria-live="polite">Submitting your answers and finding a starting point for your explanations.</p>}
    <div className="mt-6 border-t border-border pt-4 text-center">
      <button className="rounded px-2 py-1 text-xs text-muted hover:text-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
        type="button" disabled={disabled} onClick={onSkip}>{skipping ? 'Skipping calibration…' : 'Skip calibration for now'}</button>
    </div>
  </section>;
}
