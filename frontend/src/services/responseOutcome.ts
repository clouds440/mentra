import type { ResponseOutcome } from '../types/chat';

// Job workers advance independently of the conversation revision. An older
// same-revision HTTP response must not turn completed work back into working.
export function reconcileOutcome(previous?: ResponseOutcome, incoming?: ResponseOutcome): ResponseOutcome | undefined {
  if (!previous || !incoming) return incoming;
  const revisions = new Map(previous.tasks?.filter(task => task.job_id && task.job_revision != null)
    .map(task => [`${task.job_kind}:${task.job_id}`, task.job_revision!]));
  const stale = incoming.tasks?.some(task => task.job_id && task.job_revision != null
    && (revisions.get(`${task.job_kind}:${task.job_id}`) ?? -1) > task.job_revision);
  return stale ? previous : incoming;
}
