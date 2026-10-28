import type { AssessmentGeneration } from '../types/assessments';

const key = (owner: string) => `mentra.assessment-targets.v1:${owner}`;
const ttl = 60 * 60 * 1000;
let draftOwner: string | null | undefined;

export function setAssessmentTargetOwner(owner: string | null) {
  if (draftOwner === owner) return;
  draftOwner = owner;
  try {
    for (const saved of Object.keys(sessionStorage)) {
      if (saved.startsWith('mentra.assessment-targets.v1:') && (!owner || saved !== key(owner))) sessionStorage.removeItem(saved);
    }
  } catch { /* Storage may be blocked by the browser. */ }
}

export function restoreAssessmentTargets(owner: string, fallback: AssessmentGeneration, explicit: boolean): AssessmentGeneration {
  if (!owner || explicit) return fallback;
  try {
    const value = JSON.parse(sessionStorage.getItem(key(owner)) ?? 'null');
    if (!value || value.expires <= Date.now() || typeof value.context_id !== 'string' || typeof value.topic !== 'string'
        || typeof value.topic_id !== 'string' || !Array.isArray(value.concept_ids)
        || value.concept_ids.length > 20 || !value.concept_ids.every((id: unknown) => typeof id === 'string' && id.length <= 100)) return fallback;
    return {...fallback, context_id:value.context_id.slice(0,100), topic:value.topic.slice(0,200), topic_id:value.topic_id,
      concept_ids:value.concept_ids, count:Math.max(fallback.count ?? 5, value.concept_ids.length)};
  } catch { return fallback; }
}

export function rememberAssessmentTargets(owner: string, draft: AssessmentGeneration) {
  if (!owner || draftOwner !== owner) return;
  try {
    if (!draft.topic_id) { sessionStorage.removeItem(key(owner)); return; }
    sessionStorage.setItem(key(owner), JSON.stringify({expires:Date.now()+ttl, topic_id:draft.topic_id,
      topic:draft.topic, context_id:draft.context_id, concept_ids:draft.concept_ids ?? []}));
  } catch { /* Optional tab-local draft storage must never prevent practice. */ }
}
