import type { Assessment } from '../../types/assessments';

/** Explicit delivery wins; old records retain their established presentation. */
export function usesInteractiveAssessment(assessment: Assessment): boolean {
  const delivery = assessment.preferences?.delivery;
  if (delivery) return delivery === 'interactive';
  return !assessment.paper && assessment.questions.some(question =>
    !!question.options?.length || !!question.question_type && question.question_type !== 'written');
}
