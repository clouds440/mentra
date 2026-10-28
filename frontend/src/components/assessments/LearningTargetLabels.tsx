import type { AssessmentQuestion } from '../../types/assessments';

/** Saved target labels describe coverage; they never imply whole-topic mastery. */
export function LearningTargetLabels({ question }: { question: AssessmentQuestion }) {
  const targets = question.learning_targets ?? [];
  if (!targets.length) return null;
  return <ul aria-label="Skills practised" className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">{targets.map(target => <li key={target.subskill_id}>{target.topic_name && <>{target.topic_name}<span aria-hidden="true"> › </span><span className="sr-only">, subskill: </span></>}{target.subskill_name}</li>)}</ul>;
}
