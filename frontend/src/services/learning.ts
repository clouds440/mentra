import { apiRequest } from './api';
import type { ProgressExplanation } from '../types/learning';
export const progressExplanation = (id: string, context: string, signal: AbortSignal) => apiRequest<ProgressExplanation>(`/api/v1/learning/understanding/${encodeURIComponent(id)}${context ? `?context_id=${encodeURIComponent(context)}` : ''}`, { signal, cache:'no-store' });
export interface PendingConcept { id: string; label: string; context_id: string | null }
export const pendingConcepts = (signal: AbortSignal) => apiRequest<PendingConcept[]>('/api/v1/learning/concept-candidates', { signal });
export const reviewConcept = (id: string, decision: 'confirm' | 'discard', signal: AbortSignal) => apiRequest<{ status: string; concept_id: string | null }>(`/api/v1/learning/concept-candidates/${id}`, { method:'POST', signal, body:JSON.stringify({decision}) });
import type { LearningOverview, LearningProgressPage } from '../types/learning';
export const learningOverview = (signal: AbortSignal, context?: string) => apiRequest<LearningOverview>(`/api/v1/learning${context ? `?context_id=${encodeURIComponent(context)}` : ''}`, { signal });
export const learningProgress = (signal: AbortSignal, query: string, offset: number, context?: string) => {
  const params = new URLSearchParams({query, offset:String(offset), limit:'10'});
  if (context) params.set('context_id', context);
  return apiRequest<LearningProgressPage>(`/api/v1/learning/understanding?${params}`, {signal});
};
