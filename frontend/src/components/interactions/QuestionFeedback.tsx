import { CheckCircle2, CircleMinus, XCircle } from 'lucide-react';
import { MarkdownContent } from '../content/MarkdownContent';
import { AnswerContent } from '../content/AnswerContent';

export type FeedbackOutcome = 'correct' | 'partial' | 'wrong';
export const feedbackAppearance = {
  correct: { label: 'Correct', Icon: CheckCircle2, color: 'text-success', panel: 'border-success/35 bg-success/10' },
  partial: { label: 'Partially correct', Icon: CircleMinus, color: 'text-warning', panel: 'border-warning/35 bg-warning/10' },
  wrong: { label: 'Incorrect', Icon: XCircle, color: 'text-danger', panel: 'border-danger/35 bg-danger/10' },
};

/** Controlled feedback primitive, reusable without chat, assessment or API state. */
export function QuestionFeedback({ label, prompt, answer, correctAnswer, outcome, score, maxScore, feedback, misconceptions = [], showMarks = true }: {
  label: string; prompt: string; answer: string; correctAnswer?: string | null;
  outcome: FeedbackOutcome; score: number; maxScore: number; feedback: string; misconceptions?: string[]; showMarks?: boolean;
}) {
  const style = feedbackAppearance[outcome];
  return <section aria-label={`${label} feedback`} className={`min-w-0 space-y-3 rounded-xl border p-3 ${style.panel}`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-semibold text-heading">{label}</h3>
      <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${style.color}`}><style.Icon aria-hidden="true" size={16} />{style.label}{showMarks && <span className="ml-1 tabular-nums">{score}/{maxScore}</span>}</span>
    </div>
    <div className="min-w-0 break-words text-sm"><MarkdownContent content={prompt} /></div>
    <AnswerContent content={answer} />
    {correctAnswer && outcome !== 'correct' && <div className="rounded-lg border border-success/20 bg-success/5 p-3 text-sm"><p className="mb-1 text-xs font-medium text-success">Correct answer</p><MarkdownContent content={correctAnswer} /></div>}
    <div className="min-w-0 space-y-1.5 text-sm"><p className="text-xs font-semibold text-muted">Feedback</p><MarkdownContent content={feedback} />{misconceptions.length > 0 && <div className="space-y-1 border-t border-border pt-2"><p className="text-xs font-medium text-muted">What to revisit</p>{misconceptions.map((value, index) => <MarkdownContent key={index} content={value} />)}</div>}</div>
  </section>;
}
