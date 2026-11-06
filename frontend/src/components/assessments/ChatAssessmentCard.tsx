import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { memo, useEffect, useId, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { Button,IconButton } from '../ui';
import { ActionMenu } from '../ui/ActionMenu';
import { ArrowUpRight,ChevronDown,ChevronUp,MoreHorizontal } from 'lucide-react';
import { assessments } from '../../services/assessments';
import type { AssessmentAttempt, ChatAssessmentCardData } from '../../types/assessments';
import { MCQAssessment } from './MCQAssessment';
import { AnswerSheet } from './AssessmentWorkspace';
import { useAuth } from '../auth/AuthProvider';
import { assessmentSession, useLatestAssessmentAttempt } from '../../stores/assessmentSession';
import { AnswerSheetUpload } from './AnswerSheetUpload';
import { AssessmentPaper } from './AssessmentPaper';
import { usesInteractiveAssessment } from './assessmentDelivery';
import { RecoveryAnswers } from './DownloadAnswers';
import { chatStore, useConversationField } from '../../stores/chatStore';

function handoffAttempt(card: ChatAssessmentCardData) {
  const value = card.hydration;
  if(!card.assessment.questions?.length || card.assessment_id&&card.assessment.id!==card.assessment_id)return undefined;
  if (value?.version !== 1 || value.attempt && value.attempt.assessment_id !== card.assessment.id
    || !('attempt' in value) || card.attempt_id && !card.deleted && value.attempt?.id !== card.attempt_id) return undefined;
  return value.attempt;
}

export const ChatAssessmentCard = memo(function ChatAssessmentCard({ initial, hydrated = false, receivedAt,viewId }: { initial: ChatAssessmentCardData; hydrated?: boolean; receivedAt?: number;viewId:string }) {
  const navigate = useNavigate();
  const { identity } = useAuth();
  const owner = identity?.learner_id;
  const chatBusy = useConversationField(initial.conversation_id,'busy');
  const menu=useRef<HTMLButtonElement>(null),menuId=useId();
  const [menuOpen,setMenuOpen]=useState(false);
  const draftScope=`${initial.assessment.id}:view:${viewId}`;
  const meaningful=(value:ReturnType<typeof assessmentSession.draft>)=>value&&(Object.values(value.answers).some(answer=>answer.trim())||value.assistance!=='unknown') ? value : undefined;
  const [restored]=useState(()=>meaningful(assessmentSession.draft(owner,`${draftScope}:${handoffAttempt(initial)?.id??'new'}`))??meaningful(assessmentSession.draft(owner,`${draftScope}:new`)));
  const [card, setCard] = useState(()=>restored&&restored.paper.revision!==initial.assessment.revision?{...initial,assessment:restored.paper}:initial);
  const [attempt, setAttempt] = useState<AssessmentAttempt | null>(() => restored ? restored.attempt : hydrated ? handoffAttempt(initial) ?? null : null);
  const [changedElsewhere, setChangedElsewhere] = useState(false);
  const localDraft=()=>meaningful(assessmentSession.draft(owner,`${draftScope}:${attempt?.id??'new'}`));
  const hasLocalAnswers = () => !!localDraft();
  useEffect(() => {
    if (attempt && card.conversation_id) window.dispatchEvent(new CustomEvent('mentra:assessment-generation',
      {detail:{conversationId:card.conversation_id}}));
  }, [attempt?.id, attempt?.state, attempt?.revision, card.conversation_id]);
  const latest = useLatestAssessmentAttempt(card.assessment.id);
  useEffect(() => {
    if (latest && ((!initial.attempt_id && (!attempt || latest.attempt_number > attempt.attempt_number)) || latest.id === attempt?.id && latest.revision > attempt.revision)) {
      if (hasLocalAnswers() && (latest.id !== attempt?.id || latest.revision > (attempt?.revision ?? 0))) {
        setChangedElsewhere(true); setError('This assessment changed elsewhere. Your answers are kept. Refresh to review the saved attempt.');
      } else setAttempt(latest);
    }
  }, [latest, attempt, initial.attempt_id]);
  const [ready, setReady] = useState(() => hydrated && handoffAttempt(initial) !== undefined);
  useEffect(() => {
    if (!ready || receivedAt === undefined) return;
    const frame = requestAnimationFrame(() => {
      performance.clearMeasures('mentra.assessment.ready_to_visible');
      performance.measure('mentra.assessment.ready_to_visible', { start: receivedAt, end: performance.now() });
    });
    return () => cancelAnimationFrame(frame);
  }, [ready, receivedAt]);
  const [busy, setBusy] = useState(false);
  const [answerAction, setAnswerAction] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const lock = useRef(false);
  const operation = useRef(crypto.randomUUID());
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    setError('');
    const controller = new AbortController();
    if (hydrated && reload === 0 && handoffAttempt(initial) !== undefined) {
      const selected = handoffAttempt(initial);
      const changedPaper=initial.assessment.revision>card.assessment.revision||!!initial.deleted&&!card.deleted;
      if (hasLocalAnswers() && (changedPaper || selected && (selected.id !== attempt?.id || selected.revision > (attempt?.revision ?? 0)))) {
        setChangedElsewhere(true); setError('This assessment changed elsewhere. Your answers are kept. Refresh to review the saved attempt.');
      } else if (selected) {
        assessmentSession.observe(owner, selected);
        setAttempt(previous => previous?.id === selected.id && previous.revision > selected.revision ? previous : selected);
      }
      if(!changedPaper||!hasLocalAnswers())setCard(previous=>initial.assessment.revision>=previous.assessment.revision ? initial : previous);
      setReady(true);
      return () => { controller.abort(); active.current?.abort(); };
    }
    setReady(false);
    const load = hydrated && reload === 0 ? Promise.resolve(initial) : initial.id ? assessments.draft(initial.id, controller.signal,initial.attempt_id) : assessments.handoff(initial.assessment_id!, controller.signal,initial.attempt_id);
    void load.then(value => {
      const supplied = handoffAttempt({ ...value, attempt_id: initial.attempt_id });
      if (supplied===undefined) throw new Error('The assessment handoff is incomplete. Refresh to retry.');
      const selected = value.deleted ? null : supplied;
      if (selected && selected.assessment_id!==value.assessment_id) throw new Error('This attempt does not belong to this assessment.');
      if (!controller.signal.aborted) {
        const local=localDraft();
        const conflict=local&&(value.deleted||value.assessment.revision!==local.paper.revision||selected?.id!==local.attempt?.id||selected?.revision!==local.attempt?.revision);
        if(conflict){setChangedElsewhere(true);setError('This assessment changed elsewhere. Your answers are kept. Refresh to review the saved attempt.');}
        else{setCard({...value,conversation_id:initial.conversation_id,attempt_id:initial.attempt_id});setAttempt(selected);setChangedElsewhere(false);}
        if(selected)assessmentSession.observe(owner,selected);setReady(true);
      }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load assessment.'); });
    return () => { controller.abort(); active.current?.abort(); };
  }, [owner, initial.id, initial.assessment_id, initial.attempt_id, initial.hydration, hydrated, reload]);
  useEffect(()=>{
    const reviewed=(event:Event)=>{ const value=(event as CustomEvent<ChatAssessmentCardData['assessment']>).detail;
      if(value?.id===card.assessment.id) setCard(previous=>({...previous,assessment:value})); };
    window.addEventListener('mentra:assessment-reviewed',reviewed);
    return ()=>window.removeEventListener('mentra:assessment-reviewed',reviewed);
  },[card.assessment.id]);
  async function ensureSaved(signal:AbortSignal) {
    const value=card.assessment_id ? card : await assessments.publish(card.id!,signal);
    if(!signal.aborted) setCard(value);
    return value.assessment;
  }
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
    setAttempt(result);setChangedElsewhere(false);setError(''); assessmentSession.observe(owner,result);
  }
  const isMCQ = !card.deleted && usesInteractiveAssessment(card.assessment);
  function adjust(difficulty: 'easier' | 'harder') {
    if (!card.conversation_id || chatBusy || busy) return;
    const target = card.id ? `chat draft ${card.id}` : `assessment ${card.assessment_id}`;
    void chatStore.send(card.conversation_id, `Make ${target} ${difficulty}. Keep the topic, question count and delivery, and preserve the original.`,
      { mode: 'STANDARD' });
  }
  const actions = <>
    {!card.assessment_id && <Button size="sm" disabled={!ready || busy} loading={busy && !answerAction} onClick={() => void save()}>Add to assessments</Button>}
    {!card.deleted && (!attempt && !isMCQ || attempt?.state === 'graded') && <Button size="sm" variant="secondary" disabled={!ready || busy} loading={busy && answerAction} onClick={() => void save(true)}>{attempt ? 'Start new attempt' : card.assessment_id ? 'Answer in UI' : 'Add & answer'}</Button>}
  </>;
  return <section aria-label="Chat assessment" className="assessment-inline interactive-surface my-5 space-y-5">
    <div className="flex items-start justify-between gap-3" aria-label="Assessment header">
      <div className="min-w-0"><p className="mb-1 text-xs text-muted">{card.assessment.paper ? 'Mock assessment' : 'Practice'} · {card.assessment.questions.length} questions</p><h2 dir="auto" className="break-words text-lg font-medium text-heading">{card.assessment.title}</h2></div>
      {!card.deleted && <><IconButton ref={menu} aria-label="Assessment options" aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuId} onClick={()=>setMenuOpen(value=>!value)}><MoreHorizontal size={18} aria-hidden="true" /></IconButton><ActionMenu anchor={menu} id={menuId} open={menuOpen} onClose={()=>setMenuOpen(false)} label="Assessment options" align="end" items={[
        ...(card.assessment_id ? [{id:'view',label:'View in assessments',icon:ArrowUpRight,disabled:!ready,onSelect:()=>navigate(`/assessments?assessment=${card.assessment_id}`)}] : []),
        ...(!attempt && card.conversation_id ? [{id:'easier',label:'Make easier',icon:ChevronDown,disabled:!ready||busy||chatBusy,onSelect:()=>adjust('easier')},{id:'harder',label:'Make harder',icon:ChevronUp,disabled:!ready||busy||chatBusy,onSelect:()=>adjust('harder')}] : [])
      ]} /></>}
    </div>
    {card.deleted && <p className="text-sm text-muted">This assessment was deleted. Its questions remain here for reference.</p>}
    {error && <div role="alert" className="text-sm text-danger">{error} <Button variant="ghost" size="sm" onClick={() => {if(changedElsewhere)assessmentSession.archiveDraft(owner,`${draftScope}:${attempt?.id??'new'}`);setReady(false);setReload(value => value+1);}}>{changedElsewhere?'Review saved attempt':'Refresh'}</Button></div>}
    <RecoveryAnswers assessmentId={card.assessment.id} />
    {!ready ? !error && <Skeleton variant="text" rows={1} /> : isMCQ ? <MCQAssessment key={`${attempt?.id ?? card.assessment.id}:${reload}`} assessment={card.assessment} initial={attempt} draftScope={draftScope} onStart={beginInline} ensureSaved={ensureSaved} conflicted={changedElsewhere} disabled={!ready || busy || changedElsewhere} onChange={updateAttempt} actions={actions} /> : attempt ? <AnswerSheet key={`${attempt.id}:${reload}`} assessment={card.assessment} initial={attempt} draftScope={draftScope} disabled={changedElsewhere} conflicted={changedElsewhere} onChange={updateAttempt} actions={actions} /> :
      <AssessmentPaper assessment={card.assessment} />}
    {ready && !card.deleted && !isMCQ && !attempt && <AnswerSheetUpload attempt={null} onStart={beginInline} disabled={busy} onChange={updateAttempt} />}
    {(!ready && !error || !isMCQ && !attempt) && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    {!attempt && !isMCQ && <p className="text-xs text-muted">Ask questions or request changes in the chat before you begin. Revisions create a new version. When ready, send numbered answers or attach a document or handwritten image and ask Mentra to evaluate it.</p>}
  </section>;
});
