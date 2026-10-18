import type { Assessment, AssessmentAttempt } from '../../types/assessments';
import { feedbackAppearance, QuestionFeedback, type FeedbackOutcome } from '../interactions/QuestionFeedback';
import { questionLabel, selectedAnswer } from './AssessmentPaper';
import { useState } from 'react';
import { ArrowLeft, ArrowRight, List, LayoutGrid } from 'lucide-react';
import { Button } from '../ui';
import { useQuestionNavigation } from './useQuestionNavigation';
import { MistakePractice } from './MistakePractice';

/** Join by immutable question ID; model response order never determines attribution. */
export function AssessmentFeedback({ assessment, attempt }: { assessment: Assessment; attempt: AssessmentAttempt }) {
  const [view,setView]=useState<'question'|'list'>('question');
  const { index: selected, setIndex: setSelected, direction }=useQuestionNavigation();
  const grades = new Map(attempt.grades?.map(grade => [grade.question_id, grade]));
  const results = assessment.questions.flatMap((question, index) => {
    const grade = grades.get(question.id);
    if (!grade) return [];
    const outcome: FeedbackOutcome = grade.outcome ?? (grade.score === question.marks ? 'correct' : grade.score === 0 ? 'wrong' : 'partial');
    return [{ question, index, grade, outcome }];
  });
  const score = results.reduce((sum, item) => sum + item.grade.score, 0);
  const maximum = assessment.questions.reduce((sum, question) => sum + question.marks, 0);
  const style = assessment.preferences?.result_style ?? 'marks';
  const percent = maximum ? score/maximum*100 : 0;
  const current=Math.min(selected,Math.max(0,results.length-1));
  const visible=view==='list' ? results : results.slice(current,current+1);
  return <section aria-label="Assessment feedback" className="assessment-feedback min-w-0 space-y-3">
    <div className="space-y-3 rounded-xl border border-border-strong bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold text-heading">Your results</h2>{style === 'marks' && <p className="text-sm font-semibold tabular-nums text-heading">Final result: {Number(score.toFixed(4))}/{Number(maximum.toFixed(4))}</p>}</div>
      {style === 'marks' && <div className="h-1.5 overflow-hidden rounded-full bg-border" aria-hidden="true"><div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(100, percent)}%` }} /></div>}
      <div className="flex flex-wrap gap-x-3 gap-y-1.5">{(['correct', 'partial', 'wrong'] as const).map(outcome => {
        const style = feedbackAppearance[outcome];
        return <span key={outcome} className={`inline-flex items-center gap-1.5 text-xs font-medium ${style.color}`}><style.Icon aria-hidden="true" size={15} />{results.filter(item => item.outcome === outcome).length} {style.label.toLowerCase()}</span>;
      })}</div>
    </div>
    <MistakePractice key={`${attempt.id}:${attempt.grade_revision}`} assessment={assessment} attempt={attempt} />
    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-muted">{view==='list' ? `All ${results.length} results` : `Question ${current+1} of ${results.length}`}</p><Button size="sm" variant="secondary" onClick={() => setView(value=>value==='list'?'question':'list')}>{view==='list' ? <LayoutGrid size={14} aria-hidden="true" /> : <List size={14} aria-hidden="true" />}{view==='list'?'Question view':'List view'}</Button></div>
    {view==='question' && <nav aria-label="Result questions" className="flex flex-wrap gap-1.5">{results.map(({question,index,outcome},position)=><button key={question.id} type="button" aria-label={`Question ${index+1}: ${feedbackAppearance[outcome].label.toLowerCase()}`} aria-current={position===current?'step':undefined} onClick={()=>setSelected(position)} className={`grid h-8 min-w-8 place-items-center rounded-md border px-1 text-xs font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-accent ${outcome==='correct'?'border-success/40 bg-success/10 text-success':outcome==='wrong'?'border-danger/40 bg-danger/10 text-danger':'border-warning/40 bg-warning/10 text-warning'} ${position===current?'ring-2 ring-offset-1 ring-current':''}`}>{index+1}</button>)}</nav>}
    {visible.map(({ question, index, grade, outcome }) => <div key={question.id} className="question-transition" data-navigation={view==='question' ? direction : 'none'}><QuestionFeedback label={questionLabel(question, index)} prompt={[question.context, question.prompt].filter(Boolean).join('\n\n')}
      answer={selectedAnswer(question, attempt.answers[question.id])}
      correctAnswer={grade.correct_answer} outcome={outcome} score={grade.score} maxScore={question.marks} showMarks={style === 'marks'} feedback={grade.feedback} misconceptions={grade.misconceptions} /></div>)}
    {view==='question' && results.length>1 && <div className="flex gap-2"><Button size="sm" variant="secondary" disabled={current===0} onClick={()=>setSelected(value=>value-1)}><ArrowLeft size={14} aria-hidden="true" />Previous result</Button><Button size="sm" variant="secondary" disabled={current===results.length-1} onClick={()=>setSelected(value=>value+1)}>Next result<ArrowRight size={14} aria-hidden="true" /></Button></div>}
  </section>;
}
