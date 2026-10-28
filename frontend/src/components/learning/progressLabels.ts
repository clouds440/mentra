const statuses: Record<string, string> = {
  insufficient_evidence:'Getting started', needs_practice:'Needs practice', developing:'Developing',
  demonstrated:'Demonstrated', needs_verification:'Time to review',
};
const reasons: Record<string, string> = {
  insufficient_evidence:'Start with a few practice questions so Mentra can get to know your understanding.',
  low_mastery:'A little more practice can help strengthen your understanding.',
  low_estimate_confidence:'More independent practice would help make your learning estimate clearer.',
  retention_uncertain:'Revisit this topic to see how much you remember.',
  recall_unchecked:'An independent check can show how well this skill holds over time.',
  prerequisite_importance:'This topic supports other things you’re learning.',
  contradictory_evidence:'Your recent answers gave mixed results. A short check can help clarify your understanding.',
  difficulty_unverified:'Try questions at a different difficulty to see how comfortably you can apply this topic.',
};
export const progressStatus = (status: string) => statuses[status] ?? 'Getting started';
export const progressReason = (reason: string) => reasons[reason] ?? 'A short practice session can help you build on what you’ve learned.';
export const supportedReview = (reason: string) => ['low_estimate_confidence', 'retention_uncertain', 'recall_unchecked', 'contradictory_evidence'].includes(reason);
