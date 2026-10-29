import type { Assessment, AssessmentAttempt } from '../../types/assessments';
import { feedbackAppearance, QuestionFeedback, type FeedbackOutcome } from '../interactions/QuestionFeedback';
import { questionLabel, selectedAnswer } from './AssessmentPaper';
import { useState } from 'react';
import { ArrowLeft, ArrowRight, X } from 'lucide-react';
import { Button, Dialog, IconButton } from '../ui';
import { ViewToggle } from '../ui/ViewToggle';
import { useQuestionNavigation } from './useQuestionNavigation';
import { MistakePractice } from './MistakePractice';
import { LearningTargetGroups, LearningTargetLabels } from './LearningTargetLabels';

/** Join by immutable question ID; model response order never determines attribution. */
export function AssessmentFeedback({ assessment, attempt }: { assessment: Assessment; attempt: AssessmentAttempt }) {
  const [view,setView]=useState<'grid'|'list'>('grid');
  const [reviewOpen, setReviewOpen] = useState(false);
  const { index: selected, setIndex: setSelected, direction }=useQuestionNavigation();
  const grades = new Map(attempt.grades?.map(grade => [grade.question_id, grade]));
  const results = assessment.questions.flatMap((question, index) => {
    const grade = grades.get(question.id);
    if (!grade) return [];
    const outcome: FeedbackOutcome = grade.outcome ?? (grade.score === question.marks ? 'correct' : grade.score === 0 ? 'wrong' : 'partial');
    return [{ question, index, grade, outcome }];
  });
  const rawScore = results.reduce((sum, item) => sum + item.grade.score, 0);
  const score = attempt.scoring?.adjusted_score ?? rawScore;
  const maximum = assessment.questions.reduce((sum, question) => sum + question.marks, 0);
  const style = assessment.preferences?.result_style ?? 'marks';
  const percent = maximum ? score/maximum*100 : 0;
  const current=Math.min(selected,Math.max(0,results.length-1));
  const visible = results.slice(current,current+1);
  const renderFeedback = ({question, index, grade, outcome}: typeof results[number]) => <div className="space-y-2"><LearningTargetLabels question={question} /><QuestionFeedback label={questionLabel(question, index)} prompt={[question.context, question.prompt].filter(Boolean).join('\n\n')} answer={selectedAnswer(question, attempt.answers[question.id])} correctAnswer={grade.correct_answer} outcome={outcome} score={grade.score} maxScore={question.marks} showMarks={style === 'marks'} feedback={grade.feedback} misconceptions={grade.misconceptions} /></div>;
  return <section aria-label="Assessment feedback" className="assessment-feedback min-w-0 space-y-3">
    <div className="space-y-3 rounded-xl border border-border-strong bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold text-heading">Your results</h2>{style === 'marks' && <p className="text-sm font-semibold tabular-nums text-heading">Final result: {Number(score.toFixed(4))}/{Number(maximum.toFixed(4))}</p>}</div>
      {attempt.scoring?.multiplier === .9 && <p className="text-xs leading-5 text-muted">{style === 'marks' ? `Raw score: ${attempt.scoring.raw_score}/${attempt.scoring.max_score}. ` : ''}Self-reported AI/hint use: 0.9× final-score adjustment applied. Question marks and correctness show the original rubric result.</p>}
      {style === 'marks' && <div className="h-1.5 overflow-hidden rounded-full bg-border" aria-hidden="true"><div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, percent)}%` }} /></div>}
      <div className="flex flex-wrap gap-x-3 gap-y-1.5">{(['correct', 'partial', 'wrong'] as const).map(outcome => {
        const style = feedbackAppearance[outcome];
        return <span key={outcome} className={`inline-flex items-center gap-1.5 text-xs font-medium ${style.color}`}><style.Icon aria-hidden="true" size={15} />{results.filter(item => item.outcome === outcome).length} {style.label.toLowerCase()}</span>;
      })}</div>
    </div>
    {!!assessment.questions.some(question => question.learning_targets?.length) && <section aria-label="Topics covered" className="rounded-control border border-border p-3"><h3 className="text-sm font-medium text-heading">Skills checked in this assessment</h3><p className="mt-1 text-xs text-muted">These results apply to the listed subskills. Other skills in each topic remain untested.</p><div className="mt-2"><LearningTargetGroups stacked targets={assessment.questions.flatMap(question => question.learning_targets ?? [])} /></div></section>}
    <MistakePractice key={`${attempt.id}:${attempt.grade_revision}`} assessment={assessment} attempt={attempt} />
    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-muted">All {results.length} results</p><ViewToggle label="Result view" view={view} onChange={setView} /></div>
    {view === 'grid' ? <div className="workspace-compact-grid">{results.map((item, position) => {
      const appearance = feedbackAppearance[item.outcome];
      return <article key={item.question.id} className="workspace-panel flex h-56 min-w-0 flex-col gap-3 overflow-hidden">
        <div className="flex min-w-0 items-center justify-between gap-2"><span className="truncate text-xs font-medium text-heading">{questionLabel(item.question, item.index)}</span>{style === 'marks' && <span className="shrink-0 text-xs tabular-nums text-muted">{item.grade.score}/{item.question.marks}</span>}</div>
        <p className="line-clamp-2 h-10 break-words text-sm font-medium leading-5 text-heading" title={item.question.prompt}>{item.question.prompt}</p>
        <span className={`flex items-center gap-1.5 text-xs ${appearance.color}`}><appearance.Icon size={14} aria-hidden="true" />{appearance.label}</span>
        <p className="line-clamp-2 h-8 break-words text-xs leading-4 text-muted" title={item.grade.feedback}>{item.grade.feedback}</p>
        <Button size="sm" variant="secondary" className="mt-auto w-full" onClick={() => { setSelected(position); setReviewOpen(true); }}>Review result</Button>
      </article>;
    })}</div> : results.map(item => <div key={item.question.id}>{renderFeedback(item)}</div>)}
    {reviewOpen && <Dialog open onDismiss={() => setReviewOpen(false)} aria-labelledby="result-review-title" className="max-w-2xl">
      <div className="mb-4 flex items-center justify-between gap-3"><h2 id="result-review-title" className="font-medium text-heading">Question {current+1} of {results.length}</h2><IconButton aria-label="Close result review" onClick={() => setReviewOpen(false)}><X size={18} /></IconButton></div>
      <nav aria-label="Result questions" className="mb-4 flex flex-wrap gap-1.5">{results.map(({question,index,outcome},position)=><button key={question.id} type="button" aria-label={`Question ${index+1}: ${feedbackAppearance[outcome].label.toLowerCase()}`} aria-current={position===current?'step':undefined} onClick={()=>setSelected(position)} className={`ui-button grid min-h-8 min-w-8 place-items-center rounded-control border px-1 text-xs font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-accent ${outcome==='correct'?'border-success/40 bg-success/10 text-success':outcome==='wrong'?'border-danger/40 bg-danger/10 text-danger':'border-warning/40 bg-warning/10 text-warning'} ${position===current?'ring-2 ring-offset-1 ring-current':''}`}>{index+1}</button>)}</nav>
      {visible.map(item => <div key={item.question.id} className="question-transition" data-navigation={direction}>{renderFeedback(item)}</div>)}
      {results.length>1 && <div className="mt-4 flex justify-between gap-2"><Button size="sm" variant="secondary" disabled={current===0} onClick={()=>setSelected(value=>value-1)}><ArrowLeft size={14} aria-hidden="true" />Previous result</Button><Button size="sm" variant="secondary" disabled={current===results.length-1} onClick={()=>setSelected(value=>value+1)}>Next result<ArrowRight size={14} aria-hidden="true" /></Button></div>}
    </Dialog>}
  </section>;
}
