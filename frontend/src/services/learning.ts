import { apiRequest } from './api';
import type { LearningOverview } from '../types/learning';
export const learningOverview = (signal: AbortSignal, context?: string) => apiRequest<LearningOverview>(`/api/v1/learning${context ? `?context_id=${encodeURIComponent(context)}` : ''}`, { signal });
