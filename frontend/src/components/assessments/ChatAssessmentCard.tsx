import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { assessments } from '../../services/assessments';
import type { AssessmentAttempt, ChatAssessmentCardData } from '../../types/assessments';
import { MCQAssessment } from './MCQAssessment';
import { AnswerSheet } from './AssessmentWorkspace';

export function ChatAssessmentCard({ initial }: { initial: ChatAssessmentCardData }) {
  const navigate = useNavigate();
  const [card, setCard] = useState(initial);
  const [attempt, setAttempt] = useState<AssessmentAttempt | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const lock = useRef(false);
  const operation = useRef(crypto.randomUUID());
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    setReady(false); setError('');
    const controller = new AbortController();
    const load = initial.id ? assessments.draft(initial.id, controller.signal) : assessments.detail(initial.assessment_id!, controller.signal).then(assessment => ({ ...initial, assessment }));
    void load.then(async value => {
      const selected = value.deleted ? null : initial.attempt_id ? await assessments.attempt(initial.attempt_id, controller.signal) :
        value.assessment_id ? (await assessments.attempts(value.assessment_id, controller.signal))[0] ?? null : null;
      if (selected && selected.assessment_id!==value.assessment_id) throw new Error('This attempt does not belong to this assessment.');
      if (!controller.signal.aborted) { setCard(value); setAttempt(selected); setReady(true); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load assessment.'); });
    return () => { controller.abort(); active.current?.abort(); };
  }, [initial.id, initial.assessment_id, initial.attempt_id, reload]);
  async function save(answer = false) {
    if (lock.current) return;
    lock.current = true;
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try {
      const value = card.assessment_id ? card : await assessments.publish(card.id!, controller.signal);
      const result = answer ? await assessments.start(value.assessment_id!, operation.current, controller.signal) : null;
      if (!controller.signal.aborted) { setCard(value); if (result) { setAttempt(result); operation.current = crypto.randomUUID(); } }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to save assessment.'); }
    finally { lock.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  async function beginInline(signal: AbortSignal) {
    const value = card.assessment_id ? card : await assessments.publish(card.id!, signal);
    if (!signal.aborted) setCard(value);
    const result = await assessments.start(value.assessment_id!, operation.current, signal);
    if (!signal.aborted) operation.current = crypto.randomUUID();
    return result;
  }
  const isMCQ = !card.deleted && card.assessment.questions.every(q => !!q.options?.length);
  const InlineAnswers = card.assessment.questions.every(q => !!q.options?.length) ? MCQAssessment : AnswerSheet;
  const actions = <>
    {!card.assessment_id && <Button size="sm" disabled={!ready || busy} loading={busy} onClick={() => void save()}>Add to assessments</Button>}
    {!card.deleted && (!attempt && !isMCQ || !!attempt && ['graded','failed'].includes(attempt.state)) && <Button size="sm" variant="secondary" disabled={!ready || busy} loading={busy} onClick={() => void save(true)}>{attempt ? 'Try again' : card.assessment_id ? 'Answer or upload work' : 'Add & answer'}</Button>}
    {card.assessment_id && !card.deleted && <Button size="sm" variant="secondary" onClick={() => navigate(`/assessments?assessment=${card.assessment_id}`)}>View in assessments</Button>}
  </>;
  return <section aria-label="Chat assessment" className="my-4 space-y-4 rounded-xl border border-border p-4">
    <h2 className="font-medium text-heading">{card.assessment.title}</h2>
    <p className="text-sm text-muted">{card.deleted ? 'This assessment was deleted. Its questions remain here for reference.' : card.assessment_id ? 'Saved to your assessments.' : 'This practice stays in this chat until you add it or submit answers for evaluation.'}</p>
    {error && <p role="alert" className="text-sm text-danger">{error} <button className="underline" onClick={() => setReload(value => value+1)}>Refresh</button></p>}
    {!ready && !error ? <Skeleton variant="card" rows={1} /> : isMCQ ? <MCQAssessment key={attempt?.id ?? card.assessment.id} assessment={card.assessment} initial={attempt} onStart={beginInline} disabled={!ready || busy} onChange={setAttempt} actions={actions} /> : attempt ? <InlineAnswers key={attempt.id} assessment={card.assessment} initial={attempt} onChange={setAttempt} actions={actions} /> :
      <ol className="space-y-4">{card.assessment.questions.map((question,index) => <li key={question.id}><p className="text-sm text-muted">Question {index+1} · {question.marks} marks</p><MarkdownContent content={question.prompt} /></li>)}</ol>}
    {(!ready && !error || !isMCQ && !attempt) && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    {!attempt && !isMCQ && <p className="text-xs text-muted">Ask questions or request changes in the chat before you begin. Revisions create a new version. When ready, send numbered answers or attach a document or handwritten image and ask Mentra to evaluate it.</p>}
  </section>;
}
