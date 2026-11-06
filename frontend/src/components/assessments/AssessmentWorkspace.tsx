import { PageShell, PageSkeleton } from '../workspace/PageShell';
import { AssistanceSelector } from './AssistanceSelector';
import { AnswerSheetUpload } from './AnswerSheetUpload';
import { PrintPaperButton } from './PrintPaperButton';
import { MistakesPractice } from './MistakesPractice';
import { AttemptBadges } from './AttemptBadges';
import { Tabs } from '../ui/Tabs';
import { ClipboardCheck, ArrowUpRight, Sparkles, LoaderCircle } from 'lucide-react';
import { WorkspaceHeader, WorkspaceEmpty } from '../workspace/WorkspaceHeader';
import { materialWarningMessage } from '../../services/userError';
import { usePageRefresh, refreshPage } from '../../hooks/usePageRefresh';
import { ApiError } from '../../services/api';
import { AssessmentFeedback } from './AssessmentFeedback';
import { AssessmentPaper, PaperHeader, PracticeNotice, questionLabel, selectedIds, selectedAnswer, showsAssessmentMarks } from './AssessmentPaper';
import { MCQAssessment } from './MCQAssessment';
import { usesInteractiveAssessment } from './assessmentDelivery';
import { AssessmentGenerationCard } from './AssessmentGenerationCard';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { Toggle } from '../ui/Toggle';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { useAuth } from '../auth/AuthProvider';
import { Button, Textarea } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { AnswerContent } from '../content/AnswerContent';
import { assessments } from '../../services/assessments';
import { practiceDraft } from '../../services/practiceIntent';
import { restoreAssessmentTargets, rememberAssessmentTargets } from '../../services/assessmentTargetDraft';
import { AssessmentCreateForm } from './AssessmentCreateForm';
import type { Assessment, AssessmentListItem, AssessmentAttempt, AssessmentGeneration,AssessmentHydration,ChatAssessmentCardData } from '../../types/assessments';
import type { LearningContext } from '../../types/rag';
import { assessmentSession, useEvaluatedAttempt } from '../../stores/assessmentSession';
import { QuizAnswerReview } from './QuizAnswerReview';
import { DownloadAnswers,DraftStorageNotice,RecoveryAnswers } from './DownloadAnswers';
import { ItemReview,QuarantineNotice,useItemQuarantine } from './ItemReview';

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
  const visible=useRef({assessment:current,attempt});visible.current={assessment:current,attempt};
  const [changedElsewhere,setChangedElsewhere]=useState(false);
  const deliveredAt=useRef<number|undefined>(undefined);
  const pendingSnapshot=useRef<{assessment:Assessment;attempt:AssessmentAttempt|null}|null>(null);
  const [deliveryRevision,setDeliveryRevision]=useState(0);
  const localStart=useRef<string|null>(null);
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
  const generationOperation = useRef<{ payload: string; id: string }>(undefined);
  usePageRefresh(() => setReload(value => value + 1), !busy && !attempt, ['assessments']);
  useEffect(() => {
    if (tab === 'mistakes') { setLoading(false); return; }
    const controller = new AbortController();
    const generatingHere=!!params.get('generation');
    setLoading(generatingHere&&deliveredAt.current!==undefined ? false : id ? current?.id!==id : items.length===0);setError('');
    if(id&&current?.id!==id||!id&&!generatingHere&&current){setCurrent(null);setAttempt(null);setChangedElsewhere(false);}
    void assessments.page(controller.signal, tab, id).then(page => {
      const history = page.attempts;
      if (!controller.signal.aborted) {
        if (tab === 'assessments') { setItems(page.items); setMore(page.next_offset); } if (tab === 'create') setContexts(page.contexts);
        const selected=attemptId ? history.find(item=>item.id===attemptId)??null : history.find(item=>item.state!=='draft'||Object.keys(item.answers).length>0)??history[0]??null;
        const live=visible.current;
        const dirty=Object.values(assessmentSession.draft(owner,`${live.assessment?.id}:${live.attempt?.id??'new'}`)?.answers??{}).some(value=>value.trim());
        const same=!!live.assessment&&!!page.detail&&live.assessment.id===page.detail.id;
        const older=same&&(page.detail!.revision<live.assessment!.revision||live.attempt&&(!selected||!attemptId&&selected.attempt_number<live.attempt.attempt_number||selected.id===live.attempt.id&&selected.revision<live.attempt.revision));
        const startingHere=same&&!live.attempt&&selected?.id===localStart.current;
        if(!older&&!startingHere){
          if(dirty&&same&&(page.detail!.revision>live.assessment!.revision||selected?.id!==live.attempt?.id||selected&&selected.revision>(live.attempt?.revision??0))){pendingSnapshot.current={assessment:page.detail!,attempt:selected};setChangedElsewhere(true);setError('This assessment changed elsewhere. Your answers are kept. Review the saved attempt before continuing.');}
          else{setCurrent(page.detail);setAttempt(selected);setChangedElsewhere(false);}
        }
        setAttempts(live.attempt&&same ? [live.attempt,...history.filter(value=>value.id!==live.attempt!.id)] : history);
      }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load assessments.'); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); active.current?.abort(); };
  }, [id, attemptId, reload, tab]);
  useEffect(()=>{
    if(!current||deliveredAt.current===undefined)return;
    const frame=requestAnimationFrame(()=>performance.measure('mentra.assessment.workspace_ready_to_visible',{start:deliveredAt.current!,end:performance.now()}));
    return ()=>cancelAnimationFrame(frame);
  },[current?.id]);
  useEffect(()=>{
    const review=(event:Event)=>{const value=(event as CustomEvent<Assessment>).detail;if(value?.id===current?.id)setCurrent(value);};
    window.addEventListener('mentra:assessment-reviewed',review);return ()=>window.removeEventListener('mentra:assessment-reviewed',review);
  },[current?.id]);
  function generated(result:Assessment|ChatAssessmentCardData,hydration:AssessmentHydration,receivedAt?:number){
    const assessment='assessment' in result ? result.assessment : result;
    deliveredAt.current=receivedAt;setCurrent(assessment);setAttempt(hydration.attempt);setAttempts(hydration.attempt?[hydration.attempt]:[]);setLoading(false);setChangedElsewhere(false);setParams({assessment:assessment.id});
  }
  function reconcile(){
    const next=pendingSnapshot.current;if(!next)return;
    assessmentSession.archiveDraft(owner,`${current?.id}:${attempt?.id??'new'}`);
    setCurrent(next.assessment);setAttempt(next.attempt);setChangedElsewhere(false);setError('');setDeliveryRevision(value=>value+1);pendingSnapshot.current=null;
  }
  function updateAttempt(result: AssessmentAttempt) {
    localStart.current=null;setAttempt(result);setChangedElsewhere(false);setError('');
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
    if (!current || changedElsewhere || current.questions.some(q=>q.validation?.state==='invalidated')) return;
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try { const result = await assessments.start(current.id, startOperation.current, controller.signal); if (!controller.signal.aborted) { updateAttempt(result); startOperation.current = crypto.randomUUID(); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to start attempt.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function beginWorkspaceInline(signal:AbortSignal){
    if(!current)throw new Error('Assessment unavailable.');
    const value=await assessments.start(current.id,startOperation.current,signal);
    if(!signal.aborted){localStart.current=value.id;startOperation.current=crypto.randomUUID();}
    return value;
  }
  async function loadMore() {
    if (more === null) return; const controller = new AbortController(); active.current = controller;
    try { const result = await assessments.page(controller.signal, 'assessments', undefined, more); if (!controller.signal.aborted) { setItems(previous => [...previous, ...result.items]); setMore(result.next_offset); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load more assessments.'); }
  }
  return <PageShell>
    <WorkspaceHeader title="Assessments" description="Build understanding through practice. Create questions, continue an attempt or revisit your mistakes." icon={ClipboardCheck} />
    <Tabs label="Assessment sections" value={tab} onChange={changeTab} options={(['assessments', 'mistakes', 'create'] as const).map(value => ({ value, label: value === 'create' ? 'Create new' : value === 'mistakes' ? 'Practice my mistakes' : 'Assessments', id: `assessment-tab-${value}`, panel: `assessment-panel-${value}`, disabled: busy }))} />
    {error && <div role="alert" className="text-sm text-danger">{error} {changedElsewhere?<Button variant="ghost" size="sm" onClick={reconcile}>Review saved attempt</Button>:<Button variant="ghost" size="sm" onClick={() => refreshPage(() => setReload(value => value + 1))}>Refresh</Button>}</div>}
    <section role="tabpanel" id="assessment-panel-mistakes" aria-labelledby="assessment-tab-mistakes" hidden={tab !== 'mistakes'}>{tab === 'mistakes' && <MistakesPractice />}</section>
    <section role="tabpanel" id="assessment-panel-create" aria-labelledby="assessment-tab-create" hidden={tab !== 'create'}>
    {params.get('generation') && <AssessmentGenerationCard key={params.get('generation')!} id={params.get('generation')!} title="Your assessment" onComplete={generated} />}
    {loading && !error ? <PageSkeleton layout="form" /> : <AssessmentCreateForm topics={contexts.map(item => item.name)} draft={draft} onChange={setDraft} busy={busy} onSubmit={() => void generate()} />}
    </section>
    <section role="tabpanel" id="assessment-panel-assessments" aria-labelledby="assessment-tab-assessments" hidden={tab !== 'assessments'} className="space-y-5">
    {loading && !error && <PageSkeleton />}
    {current && <section className="interactive-surface space-y-5"><div className="flex flex-wrap items-center justify-between gap-2"><h2 dir="auto" className="text-xl font-medium text-heading">{current.title}</h2>{(attempt||!usesInteractiveAssessment(current))&&<Button variant="secondary" disabled={busy||changedElsewhere||current.questions.some(q=>q.validation?.state==='invalidated')} loading={busy} onClick={() => void start()}>{attempt?'Start new attempt':'Answer in UI'}</Button>}</div>
      <RecoveryAnswers assessmentId={current.id}/>{usesInteractiveAssessment(current)&&(!attempt||attempt.state==='draft') ? <MCQAssessment key={`${attempt?.id??current.id}:${deliveryRevision}`} assessment={current} initial={attempt} onStart={beginWorkspaceInline} disabled={changedElsewhere||busy} conflicted={changedElsewhere} onChange={updateAttempt}/> : attempt ? <AnswerSheet key={`${attempt.id}:${deliveryRevision}`} assessment={current} initial={attempt} disabled={changedElsewhere} conflicted={changedElsewhere} onChange={updateAttempt}/> : <><AssessmentPaper assessment={current}/><AnswerSheetUpload attempt={null} onBusyChange={setBusy} disabled={busy} onStart={beginWorkspaceInline} onChange={updateAttempt}/></>}
      <details className="text-sm text-muted"><summary className="ui-disclosure cursor-pointer py-2">Attempt history ({attempts.length})</summary>{attempts.length === 0 && <p className="text-sm text-muted">No attempts yet.</p>}<ul className="space-y-2">{attempts.map(value => <li key={value.id}><button type="button" aria-pressed={attempt?.id === value.id} className="w-full rounded-control border border-border px-3 py-2.5 text-left text-sm text-heading transition-colors duration-150 hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent aria-pressed:border-accent aria-pressed:bg-active" onClick={() => {setAttempt(value);setChangedElsewhere(false);setError('');}}>Attempt {value.attempt_number} · {value.state} · {new Date(value.created_at).toLocaleString()}</button></li>)}</ul></details>
    </section>}
    <h2 className="text-lg font-medium">Your assessments</h2>{!loading && !error && items.length === 0 && <WorkspaceEmpty icon={Sparkles} title="Practice starts with a question" description="Use the Create new tab to build practice around a topic. Your attempts and feedback stay together here." />}<ul className="workspace-grid">{items.map(item => <li key={item.id}><button className="workspace-item flex h-full w-full items-start gap-3 text-left text-heading focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setParams({ assessment: item.id })}><span className="grid h-8 w-8 shrink-0 place-items-center rounded-control bg-active text-accent"><ClipboardCheck size={19} aria-hidden="true" /></span><span className="min-w-0 flex-1"><span className="block break-words font-medium">{item.title}</span><span className="mt-2 block text-xs text-muted">{item.question_count} questions{item.has_paper ? ` · ${item.part_count} parts` : ''}</span><span className="workspace-status mt-3 capitalize">{item.tags?.includes('revision assessment') ? 'Revision assessment' : item.purpose}</span><AttemptBadges summary={item.attempt_summary} /></span><ArrowUpRight size={16} className="shrink-0 text-subtle" aria-hidden="true" /></button></li>)}</ul>{more !== null && <Button variant="secondary" onClick={() => void loadMore()}>Load more</Button>}
    </section>
  </PageShell>;
}

export function AnswerSheet({ assessment, initial, onChange, actions,disabled=false,conflicted=false,draftScope }: { assessment: Assessment; initial: AssessmentAttempt; onChange: (attempt: AssessmentAttempt) => void; actions?: ReactNode;disabled?:boolean;conflicted?:boolean;draftScope?:string }) {
  const { identity } = useAuth();
  const owner = identity?.learner_id;
  const canonical = useEvaluatedAttempt(initial.id);
  const signature=JSON.stringify([assessment.revision,assessment.questions.map(q=>[q.id,q.options?.map(o=>o.id)])]);
  const draftKey=`${draftScope??assessment.id}:${initial.id}`;
  const [restored]=useState(()=>{const value=assessmentSession.draft(owner,draftKey);return value&&(Object.values(value.answers).some(answer=>answer.trim())||value.assistance!=='unknown')?value:undefined;});
  const different=!!restored && assessment.questions.some(q=>(restored.answers[q.id]??'')!==(initial.answers[q.id]??''));
  const dirty=useRef(different);
  const [attempt, setAttempt] = useState(different && restored?.attempt ? restored.attempt : initial);
  const [conflict,setConflict]=useState<AssessmentAttempt|null>(different && restored?.attempt?.revision!==initial.revision ? initial : null);
  const [answers, setAnswers] = useState(restored?.answers ?? (initial.state==='pending_transcription' ? initial.extraction?.answers ?? initial.answers : initial.answers));
  const [confirmed, setConfirmed] = useState(false);
  const [assistance, setAssistance] = useState<'unknown' | 'independent' | 'assisted'>(restored?.assistance ?? initial.reported_assistance ?? initial.assistance ?? 'unknown');
  const [correcting, setCorrecting] = useState(different && initial.state==='graded');
  const [busy, setBusy] = useState(false);
  const [activeAction, setActiveAction] = useState<'submit' | 'save' | 'retry'>();
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  const operation = useRef(restored?.operation ?? crypto.randomUUID());
  const quarantined=useItemQuarantine(assessment);
  const blocked=disabled||busy||quarantined||!!conflict;
  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => { assessmentSession.observe(owner, attempt); }, [owner, attempt.id, attempt.state, attempt.revision, attempt.retry_pending, attempt.source_pending]);
  useEffect(() => { if (canonical && canonical !== attempt && canonical.revision >= attempt.revision) {
    if(dirty.current && canonical.revision>attempt.revision){setConflict(canonical);return;}
    if (canonical.state === 'pending_transcription' && (attempt.state !== 'pending_transcription' || attempt.extraction !== canonical.extraction)) { setAnswers(canonical.extraction?.answers ?? canonical.answers); setConfirmed(false); }
    setAttempt(canonical); onChange(canonical);
  } }, [canonical, attempt]);
  const evaluating = ['submitted','grading'].includes(attempt.state) || attempt.state === 'failed' && !!attempt.retry_pending;
  const quizPending = evaluating && usesInteractiveAssessment(assessment);
  const editable = attempt.state === 'draft' || attempt.state === 'pending_transcription' || correcting;
  useEffect(()=>{
    if(editable) assessmentSession.remember(owner,draftKey,{paper:assessment,signature,answers,index:0,assistance,operation:operation.current,attempt});
    else if(!dirty.current) assessmentSession.forget(owner,draftKey);
  },[owner,draftKey,signature,answers,assistance,attempt,editable]);
  async function submit() {
    if(blocked)return;
    const controller = new AbortController(); active.current = controller; setBusy(true); setActiveAction('submit'); setError('');
    try { const result = await (correcting ? assessments.correct : assessments.submit)(attempt, answers, operation.current, confirmed, controller.signal, assistance); if (!controller.signal.aborted) { dirty.current=false;setAttempt(result); setCorrecting(false); onChange(result); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to submit answers.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function saveProgress() {
    if (blocked || attempt.state !== 'draft') return;
    const controller = new AbortController(); active.current=controller; setBusy(true); setActiveAction('save'); setError('');
    try {
      const value = await assessments.saveDraft(attempt, Object.fromEntries(Object.entries(answers).filter(([,answer]) => answer.trim())), controller.signal, assistance);
      if (!controller.signal.aborted) { dirty.current=false;setAttempt(value); setAnswers(value.answers); onChange(value); }
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Could not save progress. Your answers are still here.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function retryEvaluation() {
    if (blocked) return;
    const controller=new AbortController(); active.current=controller; setBusy(true); setActiveAction('retry'); setError('');
    try {
      const result=await assessments.retryEvaluation(attempt,operation.current,controller.signal);
      if(!controller.signal.aborted) { setAttempt(result); assessmentSession.observe(owner,result); onChange(result); operation.current=crypto.randomUUID(); }
    } catch(reason) { if(!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Could not retry evaluation. Your submitted answers are kept.'); }
    finally { if(!controller.signal.aborted) setBusy(false); }
  }
  if (attempt.source_pending) return <section aria-label="Assessment answer sheet" className="space-y-5"><p role="status">Reading your answer sheet. You can leave this page; your assessment is saved.</p>{actions}</section>;
  return <section aria-label="Assessment answer sheet" className="space-y-5">
    <DraftStorageNotice assessment={restored?.paper??assessment} answers={answers} />
    {quarantined && <QuarantineNotice />}
    {conflicted&&!conflict&&<DownloadAnswers assessment={restored?.paper??assessment} answers={answers}/>}
    {conflict && <div className="space-y-2 text-sm text-muted"><p role="alert">This attempt changed elsewhere. Your local answers are kept.</p><DownloadAnswers assessment={restored?.paper??assessment} answers={answers} /><Button variant="secondary" size="sm" onClick={()=>{const value=conflict;if(value.state!=='draft'&&value.state!=='pending_transcription')assessmentSession.archiveDraft(owner,draftKey);setAttempt(value);setConflict(null);operation.current=crypto.randomUUID();if(value.state!=='draft'&&value.state!=='pending_transcription'){dirty.current=false;setCorrecting(false);}onChange(value);}}>{conflict.state==='draft'||conflict.state==='pending_transcription' ? 'Keep my answers with current revision' : 'View saved result'}</Button></div>}
    {attempt.source_error && <p role="alert" className="text-sm text-danger">{attempt.source_error} Upload the sheet again or enter your answers below.</p>}
    <PracticeNotice assessment={assessment} />
    <PaperHeader assessment={assessment} />

    {attempt.state==='graded' && !correcting && <AssessmentFeedback assessment={assessment} attempt={attempt} />}
    {evaluating && <p role="status" className="flex items-center gap-2 text-sm text-muted"><LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />Evaluating your answers…</p>}
    <p className="text-sm text-muted">Attempt {attempt.attempt_number} · {attempt.state === 'graded' ? 'Attempted' : attempt.state}</p>{error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {editable && !correcting && <AnswerSheetUpload attempt={attempt} draftAnswers={answers} assistance={assistance} onBusyChange={setBusy} disabled={blocked} onChange={result => { setAttempt(result); setAnswers(result.extraction?.answers ?? {}); setConfirmed(false); operation.current=crypto.randomUUID(); assessmentSession.observe(owner,result); onChange(result); }} />}
    {!assessment.paper && <PrintPaperButton assessment={assessment} />}
    {attempt.extraction && editable && <div className="space-y-2 text-sm text-muted"><p>{attempt.extraction.handwriting_support==='typed_chat' ? 'Your chat answers are ready. Check their question numbers before submitting.' : attempt.extraction.handwriting_support==='vision_requires_review' ? 'Image transcription is ready. Review every answer and its question number before submitting.' : 'Review and correct every extracted answer before submitting. Handwriting may not have been read accurately.'}</p>{attempt.extraction.warnings.map((warning,index) => <p key={index}>{materialWarningMessage(warning)}</p>)}</div>}
    {quizPending && <QuizAnswerReview assessment={assessment} answers={attempt.answers} />}
    {!quizPending && (attempt.state !== 'graded' || correcting) && assessment.questions.map((question,index) => { const grade=attempt.grades?.find(item => item.question_id===question.id); return <section key={question.id} className="space-y-2 border-t border-border pt-4">{question.section && question.section !== assessment.questions[index-1]?.section && <h3 className="text-sm font-semibold text-accent">{question.section}</h3>}<div className="flex items-center justify-between gap-2"><h3 className="text-sm font-medium">{questionLabel(question,index)}{showsAssessmentMarks(assessment) ? ` · ${question.marks} marks` : ''}</h3><ItemReview assessment={assessment} question={question} /></div>{!!question.context && <div className="text-sm leading-relaxed text-muted"><MarkdownContent content={question.context} /></div>}<MarkdownContent content={question.prompt} />
      {editable && !!question.options?.length && attempt.extraction && <p className="text-sm text-muted">Answer text to review: {answers[question.id] || 'Not answered'}</p>}
      {editable && question.options?.length ? <ChoiceOptions kind={question.answer_mode === 'multiple_choice' ? 'multiple_choice' : 'single_choice'} question={`Answer ${questionLabel(question,index).replace('Question ', '')}`} hideLegend options={question.options} selected={selectedIds(question, answers[question.id])} renderLabel={label => <MarkdownContent content={label} />} disabled={blocked} onChange={selected => { dirty.current=true;setAnswers(previous => ({ ...previous, [question.id]: question.answer_mode === 'multiple_choice' ? selected.length ? JSON.stringify(selected) : '' : selected[0] })); operation.current=crypto.randomUUID(); setConfirmed(false); }} /> : editable ? <Textarea aria-label={`Answer ${questionLabel(question,index).replace('Question ', '')}`} dir="auto" className="min-h-28 w-full"  disabled={blocked} value={answers[question.id] ?? ''} onChange={event => { dirty.current=true;setAnswers(previous => ({ ...previous, [question.id]:event.target.value })); operation.current=crypto.randomUUID(); setConfirmed(false); }} /> : <AnswerContent content={selectedAnswer(question, attempt.answers[question.id])} />}
      {grade && <div className="space-y-1 text-sm"><p className="font-medium">{showsAssessmentMarks(assessment) ? `${grade.score}/${question.marks} · ` : ''}Feedback</p><MarkdownContent content={grade.feedback} />{grade.misconceptions.map((value,i) => <p key={i} className="text-muted">{value}</p>)}</div>}
    </section>; })}
    {editable && <>{assessment.practice_source && <p className="text-xs text-muted">Earlier feedback is available, so this attempt is recorded as repeated practice.</p>}<AssistanceSelector disabled={blocked} value={assistance} onChange={value => { dirty.current=true;setAssistance(value); operation.current=crypto.randomUUID(); }} />{attempt.extraction && <Toggle label="I reviewed and corrected all extracted answers" checked={confirmed} disabled={blocked} onChange={event => setConfirmed(event.target.checked)} />}</>}
    {attempt.error && !evaluating && <p role="alert" className="text-sm text-danger">{attempt.error} Your answers are saved.</p>}
    {attempt.state==='graded' && <><p role="status" className="text-sm text-muted">{attempt.evidence_status==='pending' ? 'Results saved. Learning progress updates in the background.' : attempt.evidence_status==='applied' ? 'Feedback saved and learning progress updated.' : attempt.evidence_status==='partial' ? 'Feedback saved. Learning progress was updated where the review was confident.' : 'Feedback saved. Learning progress could not be updated for this review.'}</p></>}
    {!!attempt.grade_history.length && <details className="text-sm"><summary className="ui-disclosure cursor-pointer">Previous grade revisions</summary>{attempt.grade_history.map(history => <div key={history.grade_revision} className="space-y-2 py-3"><p className="font-medium">Revision {history.grade_revision}</p>{history.grades.map(grade => <p key={grade.question_id}>{showsAssessmentMarks(assessment) ? `${grade.score} marks · ` : ''}{grade.feedback}</p>)}</div>)}</details>}
    <div className="flex flex-wrap items-center gap-2">
      {attempt.state==='failed' && !attempt.retry_pending && <Button size="sm" loading={busy && activeAction==='retry'} disabled={blocked} onClick={() => void retryEvaluation()}>Retry evaluation</Button>}
      {editable && !correcting && attempt.state === 'draft' && <Button size="sm" variant="secondary" disabled={blocked} loading={busy && activeAction === 'save'} onClick={() => void saveProgress()}>Save progress</Button>}
      {editable && <Button size="sm" disabled={blocked || assessment.questions.some(question => !answers[question.id]?.trim()) || !!attempt.extraction && !confirmed} loading={busy && activeAction === 'submit'} onClick={() => void submit()}>{attempt.extraction ? 'Confirm text & submit' : 'Submit answers'}</Button>}
      {attempt.state === 'graded' && !correcting && <Button size="sm" variant="secondary" onClick={() => { setCorrecting(true); setAnswers(attempt.answers); setAssistance(attempt.reported_assistance ?? attempt.assistance ?? 'unknown'); setConfirmed(false); operation.current=crypto.randomUUID(); }}>Correct answers or transcription</Button>}
      {actions}
    </div>
  </section>;
}
