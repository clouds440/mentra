import type { Assessment } from '../../types/assessments';

export const assessmentViewKey=(conversation:string,message:number|string,artifact:string)=>JSON.stringify([conversation,message,artifact]);

/** Explicit delivery wins; automatic delivery follows the generated structure. */
export function usesInteractiveAssessment(assessment: Assessment): boolean {
  const delivery = assessment.preferences?.delivery;
  if (delivery) return delivery === 'interactive';
  return !assessment.paper && assessment.questions.some(question =>
    !!question.options?.length || !!question.question_type && question.question_type !== 'written');
}
