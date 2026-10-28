import { apiRequest } from './api';
import type { ProgressExplanation } from '../types/learning';
import type { LearningTopicsPage, TopicSkillsPage } from '../types/learning';
function topicParams(context: string, query: string, offset: number) {
  const params = new URLSearchParams({ query, offset: String(offset), limit: '10' });
  if (context) params.set('context_id', context);
  return params;
}
export const learningTopics = (signal: AbortSignal, context = '', query = '', offset = 0) => apiRequest<LearningTopicsPage>(`/api/v1/learning/topics?${topicParams(context, query, offset)}`, { signal });
export const topicSubskills = (id: string, signal: AbortSignal, context = '', query = '', offset = 0) => apiRequest<TopicSkillsPage>(`/api/v1/learning/topics/${encodeURIComponent(id)}/subskills?${topicParams(context, query, offset)}`, { signal });
export interface TopicGroupingPreview { proposal_id?: number; organized?: number; unresolved?: number; placements?: { topic_name: string; subskill_name: string; scope: string }[] }
export const organizeLearningTopics = (context: string, signal: AbortSignal) => apiRequest<TopicGroupingPreview>('/api/v1/learning/topics/organize', { method: 'POST', signal, body: JSON.stringify({ context_id: context }) });
export const applyTopicGrouping = (id: number, signal: AbortSignal, undo = false) => apiRequest<{ organized: number }>(`/api/v1/learning/topics/organize/${id}/${undo ? 'undo' : 'apply'}`, { method: 'POST', signal });
export const renameLearningTopic = (id: string, name: string, revision: number, signal: AbortSignal) => apiRequest(`/api/v1/learning/topics/${id}`, { method: 'PATCH', signal, body: JSON.stringify({ name, expected_revision: revision }) });
export const moveLearningSubskill = (source: string, skill: string, target: string, revision: number, operation: string, signal: AbortSignal, undo = false) => apiRequest(`/api/v1/learning/topics/${source}/subskills/${skill}/move`, { method: 'POST', signal, body: JSON.stringify({ target_topic_id: target, expected_revision: revision, client_request_id: operation, undo }) });
export const progressExplanation = (id: string, context: string, signal: AbortSignal) => apiRequest<ProgressExplanation>(`/api/v1/learning/understanding/${encodeURIComponent(id)}${context ? `?context_id=${encodeURIComponent(context)}` : ''}`, { signal, cache:'no-store' });
export interface PendingConcept { id: string; label: string; context_id: string | null }
export const pendingConcepts = (signal: AbortSignal) => apiRequest<PendingConcept[]>('/api/v1/learning/concept-candidates', { signal });
export const reviewConcept = (id: string, decision: 'confirm' | 'discard', signal: AbortSignal) => apiRequest<{ status: string; concept_id: string | null }>(`/api/v1/learning/concept-candidates/${id}`, { method:'POST', signal, body:JSON.stringify({decision}) });
import type { LearningOverview, LearningProgressPage } from '../types/learning';
export interface ProgressPageData {
  overview: LearningOverview;
  contexts: import('../types/rag').LearningContext[];
  candidates: PendingConcept[];
  understanding: LearningProgressPage;
}
export const progressPage = (signal: AbortSignal, context?: string) => apiRequest<ProgressPageData>(`/api/v1/learning/page${context ? `?context_id=${encodeURIComponent(context)}` : ''}`, { signal });
export const learningOverview = (signal: AbortSignal, context?: string) => apiRequest<LearningOverview>(`/api/v1/learning${context ? `?context_id=${encodeURIComponent(context)}` : ''}`, { signal });
export const learningProgress = (signal: AbortSignal, query: string, offset: number, context?: string) => {
  const params = new URLSearchParams({query, offset:String(offset), limit:'10'});
  if (context) params.set('context_id', context);
  return apiRequest<LearningProgressPage>(`/api/v1/learning/understanding?${params}`, {signal});
};
