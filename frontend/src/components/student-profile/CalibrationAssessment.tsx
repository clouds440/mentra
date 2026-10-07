import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check } from 'lucide-react';
import { Button, Spinner } from '../ui';
import type { CalibrationAttempt, StudentProfile } from '../../types/studentProfile';
import { completeCalibration, getCalibration, profileError, saveAnswer } from '../../services/studentProfile';

export function CalibrationAssessment({ initialAttempt, onComplete, onSkip }: {
  initialAttempt: CalibrationAttempt;
  onComplete: (profile: StudentProfile) => void;
  onSkip: () => void;
}) {
  const [attempt, setAttempt] = useState(initialAttempt);
  const [index, setIndex] = useState(() => {
    const unanswered = initialAttempt.questions.findIndex((question) => !initialAttempt.answers[question.id]);
    return unanswered < 0 ? initialAttempt.questions.length - 1 : unanswered;
  });
  const [pending, setPending] = useState<'answer' | 'finish' | 'reload' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const question = attempt.questions[index];
  useEffect(() => { heading.current?.focus(); }, [question.id]);
  async function choose(optionId: string) {
    if (busy.current || attempt.answers[question.id] === optionId) return;
    busy.current = true; setPending('answer'); setError(null);
    try { setAttempt(await saveAnswer(attempt, question.id, optionId)); }
    catch (failure) { setError(profileError(failure)); }
    finally { busy.current = false; setPending(null); }
  }
  async function finish() {
    if (busy.current) return;
    busy.current = true; setPending('finish'); setError(null);
    try { onComplete((await completeCalibration(attempt)).profile); }
    catch (failure) { setError(profileError(failure)); }
    finally { busy.current = false; setPending(null); }
  }
  async function reload() {
    busy.current = true; setPending('reload');
    try {
      const current = await getCalibration();
      if (current?.status === 'in_progress') { setAttempt(current); setError(null); }
      else window.location.reload();
    } catch (failure) { setError(profileError(failure)); }
    finally { busy.current = false; setPending(null); }
  }
  const last = index === attempt.questions.length - 1;
  return <section aria-label="Calibration assessment" aria-busy={Boolean(pending)}>
    <div className="flex items-center justify-between gap-4 text-xs text-muted">
      <p aria-live="polite">Question {index + 1} of {attempt.questions.length}</p><span>About 1–2 minutes</span>
    </div>
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-border" role="progressbar" aria-label="Assessment progress"
      aria-valuemin={0} aria-valuemax={attempt.questions.length} aria-valuenow={index + 1}>
      <div className="h-full rounded-full bg-accent transition-[width] duration-200" style={{ width: `${(index + 1) / attempt.questions.length * 100}%` }} />
    </div>
    <div key={question.id} className="auth-enter mt-7">
      <h2 ref={heading} tabIndex={-1} className="text-lg font-medium leading-7 tracking-tight text-heading outline-none">{question.prompt}</h2>
      <p className="mt-2 text-xs text-subtle">Choose one answer. This is a starting point, not a grade.</p>
      <fieldset disabled={Boolean(pending)} aria-label="Answer choices" className="mt-6 space-y-3">
        {question.options.map((option) => <label key={option.id} className="relative block cursor-pointer">
          <input type="radio" name={question.id} value={option.id} checked={attempt.answers[question.id] === option.id}
            className="peer sr-only" onChange={() => { void choose(option.id); }} />
          <span className="flex min-h-12 items-center justify-between gap-3 rounded-xl border border-border-strong bg-input px-4 py-3 text-sm leading-6 text-body transition-colors hover:bg-hover peer-checked:border-accent peer-checked:bg-active peer-checked:text-heading peer-focus-visible:ring-2 peer-focus-visible:ring-accent/40 peer-disabled:cursor-wait peer-disabled:opacity-70">
            {option.text}{attempt.answers[question.id] === option.id && <Check aria-hidden="true" className="shrink-0 text-accent" size={17} />}</span>
        </label>)}
      </fieldset>
    </div>
    {error && <div className="mt-5" role="alert"><p className="text-sm leading-6 text-danger">{error}</p>
      <Button className="mt-3" size="sm" variant="secondary" disabled={Boolean(pending)} onClick={() => { void reload(); }}>Reload assessment</Button></div>}
    <div className="mt-7 flex items-center justify-between gap-3">
      <Button variant="ghost" disabled={Boolean(pending) || index === 0} onClick={() => setIndex((value) => value - 1)}>
        <ArrowLeft aria-hidden="true" size={16} />Back</Button>
      <Button disabled={Boolean(pending) || !attempt.answers[question.id] || Boolean(last && attempt.questions.some((item) => !attempt.answers[item.id]))}
        onClick={() => { if (last) void finish(); else setIndex((value) => value + 1); }}>
        {pending && <Spinner className="h-4 w-4" label={pending === 'finish' ? 'Evaluating your results' : 'Saving your answer'} />}
        {pending === 'finish' ? 'Reading your results…' : last ? 'Finish calibration' : 'Next'}{!pending && <ArrowRight aria-hidden="true" size={16} />}</Button>
    </div>
    {pending === 'finish' && <p className="mt-4 text-center text-xs leading-5 text-muted" aria-live="polite">Your answers are saved. Mentra is finding a careful starting point for your explanations.</p>}
    <div className="mt-6 border-t border-border pt-4 text-center">
      <button className="rounded px-2 py-1 text-xs text-muted hover:text-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
        type="button" disabled={Boolean(pending)} onClick={onSkip}>Skip calibration for now</button>
    </div>
  </section>;
}
