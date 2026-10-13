import type { Assessment, AssessmentAttempt } from '../../types/assessments';
import { feedbackAppearance, QuestionFeedback, type FeedbackOutcome } from '../interactions/QuestionFeedback';

/** Join by immutable question ID; model response order never determines attribution. */
export function AssessmentFeedback({ assessment, attempt }: { assessment: Assessment; attempt: AssessmentAttempt }) {
  const grades = new Map(attempt.grades?.map(grade => [grade.question_id, grade]));
  const results = assessment.questions.flatMap((question, index) => {
    const grade = grades.get(question.id);
    if (!grade) return [];
    const outcome: FeedbackOutcome = grade.outcome ?? (grade.score === question.marks ? 'correct' : grade.score === 0 ? 'wrong' : 'partial');
    return [{ question, index, grade, outcome }];
  });
  const score = results.reduce((sum, item) => sum + item.grade.score, 0);
  const maximum = assessment.questions.reduce((sum, question) => sum + question.marks, 0);
  return <section aria-label="Assessment feedback" className="assessment-feedback min-w-0 space-y-3">
    <div className="space-y-3 rounded-xl border border-border-strong bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold text-heading">Your results</h2><p className="text-sm font-semibold tabular-nums text-heading">Final result: {score}/{maximum}</p></div>
      <div className="h-1.5 overflow-hidden rounded-full bg-border" aria-hidden="true"><div className="h-full rounded-full bg-accent" style={{ width: `${maximum ? Math.min(100, score / maximum * 100) : 0}%` }} /></div>
      <div className="flex flex-wrap gap-x-3 gap-y-1.5">{(['correct', 'partial', 'wrong'] as const).map(outcome => {
        const style = feedbackAppearance[outcome];
        return <span key={outcome} className={`inline-flex items-center gap-1.5 text-xs font-medium ${style.color}`}><style.Icon aria-hidden="true" size={15} />{results.filter(item => item.outcome === outcome).length} {style.label.toLowerCase()}</span>;
      })}</div>
    </div>
    {results.map(({ question, index, grade, outcome }) => <QuestionFeedback key={question.id} label={`Question ${index + 1}`} prompt={question.prompt}
      answer={question.options?.find(option => option.id === attempt.answers[question.id])?.label ?? attempt.answers[question.id] ?? ''}
      correctAnswer={grade.correct_answer} outcome={outcome} score={grade.score} maxScore={question.marks} feedback={grade.feedback} misconceptions={grade.misconceptions} />)}
  </section>;
}
