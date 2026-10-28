import { buttonStyles } from '../ui/Button';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../ui';
import { assessments } from '../../services/assessments';
import type { AssessmentAttempt, ChatAssessmentCardData } from '../../types/assessments';
import { MCQAssessment } from './MCQAssessment';
import { AnswerSheet } from './AssessmentWorkspace';
import { useAuth } from '../auth/AuthProvider';
import { assessmentSession, useLatestAssessmentAttempt } from '../../stores/assessmentSession';
import { AnswerSheetUpload } from './AnswerSheetUpload';
import { AssessmentPaper } from './AssessmentPaper';
import { usesInteractiveAssessment } from './assessmentDelivery';
import { chatStore, useConversation } from '../../stores/chatStore';

export function ChatAssessmentCard({ initial, hydrated = false }: { initial: ChatAssessmentCardData; hydrated?: boolean }) {
  const navigate = useNavigate();
  const { identity } = useAuth();
  const owner = identity?.learner_id;
  const chat = useConversation(initial.conversation_id);
  const [card, setCard] = useState(initial);
  const [attempt, setAttempt] = useState<AssessmentAttempt | null>(null);
  useEffect(() => {
    if (attempt && card.conversation_id) window.dispatchEvent(new CustomEvent('mentra:assessment-generation',
      {detail:{conversationId:card.conversation_id}}));
  }, [attempt?.id, attempt?.state, attempt?.revision, card.conversation_id]);
  const latest = useLatestAssessmentAttempt(card.assessment.id);
  useEffect(() => { if (latest && ((!initial.attempt_id && (!attempt || latest.attempt_number > attempt.attempt_number)) || latest.id === attempt?.id && latest.revision > attempt.revision)) setAttempt(latest); }, [latest, attempt, initial.attempt_id]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [answerAction, setAnswerAction] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const lock = useRef(false);
  const operation = useRef(crypto.randomUUID());
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    setReady(false); setError('');
    const controller = new AbortController();
    const load = hydrated && reload === 0 ? Promise.resolve(initial) : initial.id ? assessments.draft(initial.id, controller.signal) : assessments.detail(initial.assessment_id!, controller.signal).then(assessment => ({ ...initial, assessment }));
    void load.then(async value => {
      const candidates = !value.deleted && !initial.attempt_id && value.assessment_id
        ? await assessments.attempts(value.assessment_id, controller.signal) : [];
      // An unused retry must not hide saved feedback when reopening a chat.
      // Keep a deliberately started retry in this session, and preserve pinned
      // attempt cards rather than silently replacing historical results.
      const selected = value.deleted ? null : initial.attempt_id ? await assessments.attempt(initial.attempt_id, controller.signal) :
        candidates.find(item => item.state !== 'draft' || Object.keys(item.answers).length > 0
          || Object.values(assessmentSession.draft(owner, `${value.assessment_id}:${item.id}`)?.answers ?? {}).some(answer=>answer.trim())) ?? candidates[0] ?? null;
      if (selected && selected.assessment_id!==value.assessment_id) throw new Error('This attempt does not belong to this assessment.');
      if (!controller.signal.aborted) { setCard(value); setAttempt(selected); if (selected) assessmentSession.observe(owner, selected); setReady(true); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load assessment.'); });
    return () => { controller.abort(); active.current?.abort(); };
  }, [owner, initial.id, initial.assessment_id, initial.attempt_id, hydrated, reload]);
  async function save(answer = false) {
    if (lock.current) return;
    lock.current = true;
    const controller = new AbortController(); active.current = controller; setBusy(true); setAnswerAction(answer); setError('');
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
    return result;
  }
  function updateAttempt(result: AssessmentAttempt) {
    if (result.id !== attempt?.id) operation.current = crypto.randomUUID();
    setAttempt(result); assessmentSession.observe(owner,result);
  }
  const isMCQ = !card.deleted && usesInteractiveAssessment(card.assessment);
  const InlineAnswers = isMCQ ? MCQAssessment : AnswerSheet;
  function adjust(difficulty: 'easier' | 'harder') {
    if (!card.conversation_id || chat.busy || busy) return;
    const target = card.id ? `chat draft ${card.id}` : `assessment ${card.assessment_id}`;
    void chatStore.send(card.conversation_id, `Make ${target} ${difficulty}. Keep the topic, question count and delivery, and preserve the original.`,
      { mode: 'STANDARD' });
  }
  const actions = <>
    {!card.assessment_id && <Button size="sm" disabled={!ready || busy} loading={busy && !answerAction} onClick={() => void save()}>Add to assessments</Button>}
    {!card.deleted && (!attempt && !isMCQ || attempt?.state === 'graded') && <Button size="sm" variant="secondary" disabled={!ready || busy} loading={busy && answerAction} onClick={() => void save(true)}>{attempt ? 'Start new attempt' : card.assessment_id ? 'Answer in UI' : 'Add & answer'}</Button>}
    {!card.deleted && !attempt && card.conversation_id && <details className="text-xs text-muted"><summary className="cursor-pointer rounded-control px-2 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">Practice options</summary><div className="mt-1 flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={!ready || busy || chat.busy} onClick={() => adjust('easier')}>Make easier</Button><Button variant="secondary" size="sm" disabled={!ready || busy || chat.busy} onClick={() => adjust('harder')}>Make harder</Button></div></details>}
  </>;
  return <section aria-label="Chat assessment" className="my-4 space-y-4 rounded-xl border border-border p-4">
    <div className="flex flex-col items-start justify-between gap-2 sm:flex-row sm:gap-3" aria-label="Assessment header">
      <h2 className="min-w-0 flex-1 break-words font-medium text-heading">{card.assessment.title}</h2>
      {card.assessment_id && !card.deleted && <Button className="shrink-0" size="sm" variant="secondary" disabled={!ready} onClick={() => navigate(`/assessments?assessment=${card.assessment_id}`)}>View in assessments</Button>}
    </div>
    <p className="text-sm text-muted">{card.deleted ? 'This assessment was deleted. Its questions remain here for reference.' : card.assessment_id ? 'Saved to your assessments.' : 'This practice stays in this chat until you add it or submit answers for evaluation.'}</p>
    {error && <p role="alert" className="text-sm text-danger">{error} <button type="button" className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'ml-2 mt-1' })} onClick={() => setReload(value => value+1)}>Refresh</button></p>}
    {!ready && !error ? <Skeleton variant="card" rows={1} /> : isMCQ ? <MCQAssessment key={attempt?.id ?? card.assessment.id} assessment={card.assessment} initial={attempt} onStart={beginInline} disabled={!ready || busy} onChange={updateAttempt} actions={actions} /> : attempt ? <InlineAnswers key={attempt.id} assessment={card.assessment} initial={attempt} onChange={updateAttempt} actions={actions} /> :
      <AssessmentPaper assessment={card.assessment} />}
    {ready && !card.deleted && !isMCQ && !attempt && <AnswerSheetUpload attempt={null} onStart={beginInline} disabled={busy} onChange={updateAttempt} />}
    {(!ready && !error || !isMCQ && !attempt) && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    {!attempt && !isMCQ && <p className="text-xs text-muted">Ask questions or request changes in the chat before you begin. Revisions create a new version. When ready, send numbered answers or attach a document or handwritten image and ask Mentra to evaluate it.</p>}
  </section>;
}
