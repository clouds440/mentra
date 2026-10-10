import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { assessments } from '../../services/assessments';
import type { AssessmentAttempt, ChatAssessmentCardData } from '../../types/assessments';
import { AnswerSheet } from './AssessmentWorkspace';

export function ChatAssessmentCard({ initial }: { initial: ChatAssessmentCardData }) {
  const [card, setCard] = useState(initial);
  const [attempt, setAttempt] = useState<AssessmentAttempt | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
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
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load assessment.'); });
    return () => { controller.abort(); active.current?.abort(); };
  }, [initial.id, initial.assessment_id, initial.attempt_id, reload]);
  async function save(answer = false) {
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try {
      const value = card.assessment_id ? card : await assessments.publish(card.id!, controller.signal);
      const result = answer ? await assessments.start(value.assessment_id!, operation.current, controller.signal) : null;
      if (!controller.signal.aborted) { setCard(value); if (result) { setAttempt(result); operation.current = crypto.randomUUID(); } }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to save assessment.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section aria-label="Chat assessment" className="my-4 space-y-4 rounded-xl border border-border p-4">
    <h2 className="font-medium text-heading">{card.assessment.title}</h2>
    <p className="text-sm text-muted">{card.deleted ? 'This assessment was deleted. Its questions remain here for reference.' : card.assessment_id ? 'Saved to your assessments.' : 'This practice stays in this chat until you add it or submit answers for evaluation.'}</p>
    {error && <p role="alert" className="text-sm text-danger">{error} <button className="underline" onClick={() => setReload(value => value+1)}>Refresh</button></p>}
    {attempt ? <AnswerSheet key={attempt.id} assessment={card.assessment} initial={attempt} onChange={setAttempt} /> :
      <ol className="space-y-4">{card.assessment.questions.map((question,index) => <li key={question.id}><p className="text-sm text-muted">Question {index+1} · {question.marks} marks</p><MarkdownContent content={question.prompt} /></li>)}</ol>}
    <div className="flex flex-wrap items-center gap-3">
      {!card.assessment_id && <Button disabled={!ready || busy} onClick={() => void save()}>Add to assessments</Button>}
      {!card.deleted && (!attempt || ['graded','failed'].includes(attempt.state)) && <Button variant="secondary" disabled={!ready || busy} onClick={() => void save(true)}>{attempt ? 'Try again' : card.assessment_id ? 'Answer or upload work' : 'Add & answer'}</Button>}
      {card.assessment_id && !card.deleted && <Link className="text-sm text-accent underline" to={`/assessments?assessment=${card.assessment_id}`}>View in assessments</Link>}
    </div>
    {!attempt && <p className="text-xs text-muted">Ask questions or request changes in the chat before you begin. Revisions create a new version. When ready, send numbered answers or attach a document or handwritten image and ask Mentra to evaluate it.</p>}
  </section>;
}
