import { MarkdownContent } from '../content/MarkdownContent';
import type { Assessment } from '../../types/assessments';
import { questionLabel, selectedAnswer, showsAssessmentMarks } from './AssessmentPaper';

export function QuizAnswerReview({ assessment, answers }: { assessment: Assessment; answers: Record<string, string> }) {
  return <section aria-label="Quiz answers" className="space-y-4">
    <h3 className="font-medium text-heading">Your answers</h3>
    {assessment.questions.map((question, index) => <section key={question.id} className="space-y-2 border-t border-border pt-4">
      <h4 className="text-sm font-medium">{questionLabel(question, index)}{showsAssessmentMarks(assessment) ? ` · ${question.marks} marks` : ''}</h4>
      <MarkdownContent content={question.prompt} />
      <div className="rounded-lg border border-border bg-input p-3 text-sm"><p className="mb-1 text-xs text-muted">Your answer</p>
        <MarkdownContent content={selectedAnswer(question, answers[question.id]) || 'Not answered'} />
      </div>
    </section>)}
  </section>;
}
