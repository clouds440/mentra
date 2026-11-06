import { QuestionProgress } from './QuestionProgress';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { Button, Textarea } from '../ui';
import { MarkdownContent } from '../content/MarkdownContent';
import { LearningTargetLabels } from './LearningTargetLabels';
import { ApiError } from '../../services/api';
import { assessments } from '../../services/assessments';
import type { Assessment, AssessmentAttempt } from '../../types/assessments';
import { AssistanceSelector } from './AssistanceSelector';
import { AnswerSheetUpload } from './AnswerSheetUpload';
import { PrintPaperButton } from './PrintPaperButton';
import { useEvaluatedAttempt } from '../../stores/assessmentSession';
import { AnswerSheet } from './AssessmentWorkspace';
import { useAuth } from '../auth/AuthProvider';
import { assessmentSession } from '../../stores/assessmentSession';
import { QuizAnswerReview } from './QuizAnswerReview';
import { ArrowLeft, ArrowRight, LoaderCircle } from 'lucide-react';
import { ItemReview,QuarantineNotice,useItemQuarantine } from './ItemReview';
import { DownloadAnswers,DraftStorageNotice } from './DownloadAnswers';
import { questionKind, selectedIds, showsAssessmentMarks, PracticeNotice } from './AssessmentPaper';
import { useQuestionNavigation } from './useQuestionNavigation';

export function MCQAssessment({ assessment, initial, onChange, onStart, disabled = false,conflicted=false,ensureSaved,draftScope, actions }: { assessment: Assessment; initial: AssessmentAttempt | null; onChange: (value: AssessmentAttempt) => void; onStart?: (signal: AbortSignal) => Promise<AssessmentAttempt>; disabled?: boolean;conflicted?:boolean;draftScope?:string;ensureSaved?:(signal:AbortSignal)=>Promise<Assessment>; actions?: ReactNode }) {
  const { identity } = useAuth();
  const owner = identity?.learner_id;
  const answerId=useId();
  const signature = JSON.stringify([assessment.revision, assessment.questions.map(q => [q.id, q.options?.map(option => option.id)])]);
  const key = (id?: string) => `${draftScope??assessment.id}:${id ?? 'new'}`;
  const [restored] = useState(() => {
    if (initial && initial.state !== 'draft') return undefined;
    const stored = assessmentSession.draft(owner, key(initial?.id)) ?? (initial ? assessmentSession.draft(owner, key()) : undefined);
    return stored;
  });
  const [attempt, setAttempt] = useState(restored?.attempt ?? initial);
  const dirty=useRef(!!restored && JSON.stringify(restored.answers)!==JSON.stringify(initial?.answers??{}));
  const [conflict,setConflict]=useState<AssessmentAttempt|null>(()=>restored&&initial&&(restored.attempt?.id!==initial.id||restored.attempt.revision!==initial.revision) ? initial : null);
  const [changedQuestions,setChangedQuestions]=useState(!!restored&&restored.signature!==signature);
  const quarantined=useItemQuarantine(assessment);
  const canonical = useEvaluatedAttempt(attempt?.id ?? '');
  useEffect(() => { if (canonical && canonical.revision > (attempt?.revision ?? -1)) { if(dirty.current){setConflict(canonical);}else{setAttempt(canonical); onChange(canonical);} } }, [canonical, attempt, onChange]);
  const [answers, setAnswers] = useState(() => Object.fromEntries(assessment.questions.flatMap(q => {
    const answer = (restored?.answers ?? initial?.answers ?? {})[q.id];
    return answer && (q.options?.length ? selectedIds(q, answer).length > 0 && selectedIds(q, answer).every(id => q.options!.some(option => option.id === id)) : true) ? [[q.id, answer]] : [];
  })));
  const { index, setIndex, direction } = useQuestionNavigation(() => Math.min(assessment.questions.length - 1, restored?.index ?? Math.max(0, assessment.questions.findIndex(q => !answers[q.id]))));
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const navigationBlocked = disabled || busy || uploading || !!conflict || conflicted || changedQuestions;
  const blocked = navigationBlocked || quarantined;
  const [error, setError] = useState('');
  const [assistance, setAssistance] = useState<'unknown' | 'independent' | 'assisted'>(restored?.assistance ?? initial?.reported_assistance ?? initial?.assistance ?? 'unknown');
  const active = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const operation = useRef(restored?.operation ?? crypto.randomUUID());
  const draftKey = useRef(key(initial?.id));
  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => {
    if(changedQuestions)return;
    const nextKey = key(attempt?.id);
    if (draftKey.current !== nextKey) assessmentSession.forget(owner, draftKey.current);
    draftKey.current = nextKey;
    if (attempt && attempt.state !== 'draft') { assessmentSession.forget(owner, nextKey); return; }
    assessmentSession.remember(owner, nextKey, { paper:assessment,signature, answers, index, assistance, operation: operation.current, attempt });
  }, [owner, assessment.id, signature, answers, index, assistance, attempt,changedQuestions]);
  const question = assessment.questions[index];
  const answered = assessment.questions.filter(q => !!answers[q.id]?.trim()).length;
  const finalQuestion = index === assessment.questions.length - 1;
  async function submit() {
    if (lock.current || blocked || answered !== assessment.questions.length) return;
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
      if (!controller.signal.aborted) { dirty.current=false;setConflict(null);setAttempt(result); assessmentSession.observe(owner, result); onChange(result); }
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof ApiError ? reason.message : 'Unable to submit your quiz. Your choices are kept; try again.');
        // Recover the authoritative revision after an interrupted write.
        try { if (working) { const result = await assessments.attempt(working.id, controller.signal); if (!controller.signal.aborted) {
          const same=assessment.questions.every(q=>result.answers[q.id]===answers[q.id]);
          if(result.revision>working.revision && !same){setConflict(result);}else{if(result.state!=='draft')dirty.current=false;setAttempt(result);if(result.state!=='draft')onChange(result);}
          assessmentSession.observe(owner,result);
        } } } catch { /* Keep choices and submission ID for retry. */ }
      }
    } finally { assessmentSession.end(owner, submission); lock.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  if (busy) return <section className="space-y-4"><p role="status" className="flex items-center gap-2 text-sm text-muted"><LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />Submitting your answers…</p><QuizAnswerReview assessment={assessment} answers={answers} /></section>;
  if (attempt && (attempt.state !== 'draft' || attempt.source_pending || attempt.source_error)) return <AnswerSheet assessment={assessment} draftScope={draftScope} initial={attempt} onChange={onChange} actions={actions} />;
  return <section aria-label="Interactive quiz" className="assessment-interaction space-y-4">
    <PracticeNotice assessment={assessment} />
    <DraftStorageNotice assessment={restored?.paper??assessment} answers={answers} />
    {quarantined && <QuarantineNotice />}
    {changedQuestions && <div className="space-y-2 text-sm text-muted"><p role="alert">The questions changed. Your earlier answers are kept for review.</p><DownloadAnswers assessment={restored?.paper??assessment} answers={restored?.answers??answers} /><Button variant="secondary" size="sm" onClick={()=>{assessmentSession.archiveDraft(owner,key(attempt?.id));setAnswers(previous=>Object.fromEntries(assessment.questions.flatMap(q=>{const value=previous[q.id];return value&&(!q.options?.length||selectedIds(q,value).every(id=>q.options!.some(option=>option.id===id))) ? [[q.id,value]] : [];})));setAttempt(initial);setConflict(null);setChangedQuestions(false);operation.current=crypto.randomUUID();if(initial)onChange(initial);}}>Review current questions</Button></div>}
    {(conflict||conflicted) && <div className="space-y-2 text-sm text-muted">{!conflicted && <p role="alert">This attempt changed elsewhere. Your local answers are kept.</p>}<DownloadAnswers assessment={assessment} answers={answers} />{conflict && <Button size="sm" variant="secondary" onClick={()=>{const saved=conflict;if(saved.state!=='draft')assessmentSession.archiveDraft(owner,key(attempt?.id));setAttempt(saved);setConflict(null);operation.current=crypto.randomUUID();onChange(saved);}}> {conflict.state==='draft' ? 'Keep my answers with current revision' : 'View saved result'}</Button>}</div>}
    <QuestionProgress answered={assessment.questions.map(q => !!answers[q.id]?.trim())} index={index} disabled={navigationBlocked} onNavigate={setIndex} />
    <div key={question.id} data-navigation={direction} className="question-transition quiz-question interaction-question space-y-4">
    <div className="flex items-center justify-between gap-2 text-xs text-muted"><span>{questionKind(question)}{showsAssessmentMarks(assessment) && <> · {question.marks} {question.marks === 1 ? 'mark' : 'marks'}</>}</span><ItemReview key={question.id} assessment={assessment} question={question} ensureSaved={ensureSaved} /></div>
    {question.context && <div dir="auto" className="text-sm leading-relaxed text-muted"><MarkdownContent content={question.context} /></div>}
    <div dir="auto" className="assessment-prompt"><MarkdownContent content={question.prompt} /></div>
    {question.options?.length ? <ChoiceOptions kind={question.answer_mode === 'multiple_choice' ? 'multiple_choice' : 'single_choice'} question={`Answer question ${index+1}`} hideLegend options={question.options}
      selected={selectedIds(question, answers[question.id])} disabled={blocked} renderLabel={label => <MarkdownContent content={label} />}
      onChange={selected => { dirty.current=true;setAnswers(previous => ({ ...previous, [question.id]: question.answer_mode === 'multiple_choice' ? selected.length ? JSON.stringify(selected) : '' : selected[0] })); operation.current=crypto.randomUUID(); }} /> : <div className="space-y-1.5"><label htmlFor={`${answerId}-${question.id}`} className="text-xs font-medium text-muted">Your answer</label><Textarea id={`${answerId}-${question.id}`} dir="auto" aria-label={`Answer question ${index+1}`} rows={question.question_type === 'short_answer' ? 3 : 5} disabled={blocked} value={answers[question.id] ?? ''} placeholder="Write your answer in your own words…" onChange={event => { dirty.current=true;setAnswers(previous => ({ ...previous, [question.id]: event.target.value })); operation.current=crypto.randomUUID(); }} /></div>}
    </div>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {finalQuestion && <AssistanceSelector label="Quiz assistance used" disabled={blocked} value={assistance} onChange={value => { dirty.current=true;setAssistance(value); operation.current=crypto.randomUUID(); }} />}
    <div className="flex items-center gap-2"><Button variant="ghost" className="me-auto" disabled={navigationBlocked || index===0} onClick={() => setIndex(value => value-1)}><ArrowLeft size={15} className="rtl:rotate-180" aria-hidden="true" />Back</Button><Button disabled={finalQuestion ? blocked || answered!==assessment.questions.length : navigationBlocked || !quarantined&&!answers[question.id]?.trim()} loading={busy} onClick={() => finalQuestion ? void submit() : setIndex(value => value+1)}>{finalQuestion ? 'Submit' : 'Next'}{!finalQuestion && <ArrowRight size={15} className="rtl:rotate-180" aria-hidden="true" />}</Button></div>
    <details className="assessment-details text-xs text-muted"><summary className="ui-disclosure cursor-pointer py-2">Practice details & help</summary><div className="space-y-4 py-3"><LearningTargetLabels question={question} /><p>Answers are sent together when you submit. Earlier feedback and guidance remain practice evidence.</p><div className="flex flex-wrap items-start gap-3"><PrintPaperButton assessment={assessment} />{actions}</div><AnswerSheetUpload attempt={attempt} onStart={onStart} draftAnswers={answers} assistance={assistance} onBusyChange={setUploading} disabled={blocked} onChange={result => { dirty.current=false;setAttempt(result); assessmentSession.observe(owner, result); onChange(result); }} /></div></details>
  </section>;
}
