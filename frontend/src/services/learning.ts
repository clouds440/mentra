import { apiRequest } from './api';
export interface PendingConcept { id: string; label: string; context_id: string | null }
export const pendingConcepts = (signal: AbortSignal) => apiRequest<PendingConcept[]>('/api/v1/learning/concept-candidates', { signal });
export const reviewConcept = (id: string, decision: 'confirm' | 'discard', signal: AbortSignal) => apiRequest<{ status: string; concept_id: string | null }>(`/api/v1/learning/concept-candidates/${id}`, { method:'POST', signal, body:JSON.stringify({decision}) });
import type { LearningOverview } from '../types/learning';
export const learningOverview = (signal: AbortSignal, context?: string) => apiRequest<LearningOverview>(`/api/v1/learning${context ? `?context_id=${encodeURIComponent(context)}` : ''}`, { signal });
