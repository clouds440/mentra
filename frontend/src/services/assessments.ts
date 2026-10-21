import { apiRequest } from './api';
import { uploadFile } from './files';
import type { Assessment, AssessmentAttempt, AssessmentGeneration, ChatAssessmentCardData } from '../types/assessments';
const base = '/api/v1/assessments';
export const assessments = {
  page: (signal: AbortSignal, view: 'assessments' | 'create' = 'assessments', id?: string | null, offset = 0) => {
    const params = new URLSearchParams({ view, offset: String(offset) });
    if (id) params.set('assessment_id', id);
    return apiRequest<{ items: import('../types/assessments').AssessmentListItem[]; next_offset: number | null; contexts: import('../types/rag').LearningContext[]; detail: Assessment | null; attempts: AssessmentAttempt[] }>(`${base}/page?${params}`, { signal });
  },
  mistakes: (ids: string[], topics: string[], offset: number, signal: AbortSignal) => { const query = new URLSearchParams({ offset: String(offset) }); ids.forEach(id => query.append('assessment_id', id)); topics.forEach(id => query.append('topic_id', id)); return apiRequest<import('../types/assessments').MistakesPage>(`${base}/mistakes?${query}`, { signal }); },
  reviseMistakes: (body: { client_request_id: string; assessment_ids: string[]; topic_ids: string[]; count: number }, signal: AbortSignal) => apiRequest<import('../types/assessments').GenerationJob>(`${base}/mistakes/practice`, { method: 'POST', signal, body: JSON.stringify(body) }),
  practiseMistakes: (attempt: AssessmentAttempt, question_ids: string[], operation: string, signal: AbortSignal) => apiRequest<Assessment>(`${base}/attempts/${attempt.id}/practice`, { method:'POST', signal, body:JSON.stringify({ expected_grade_revision:attempt.grade_revision, question_ids, client_request_id:operation }) }),
  retryEvaluation: (attempt: AssessmentAttempt, operation: string, signal: AbortSignal) => apiRequest<AssessmentAttempt>(`${base}/attempts/${attempt.id}/retry`, {method:'POST',signal,body:JSON.stringify({expected_revision:attempt.revision,client_request_id:operation})}),
  queue: (request: AssessmentGeneration, signal: AbortSignal) => apiRequest<import('../types/assessments').GenerationJob>(`${base}/generation-jobs`, { method: 'POST', signal, body: JSON.stringify(request) }),
  job: (id: string, signal: AbortSignal) => apiRequest<import('../types/assessments').GenerationJob>(`${base}/generation-jobs/${id}`, { signal, cache: 'no-store' }),
  retryJob: (id: string, signal: AbortSignal) => apiRequest<import('../types/assessments').GenerationJob>(`${base}/generation-jobs/${id}/retry`, { method: 'POST', signal }),
  draft: (id: string, signal: AbortSignal) => apiRequest<ChatAssessmentCardData>(`${base}/chat-drafts/${id}`, { signal }),
  publish: (id: string, signal: AbortSignal) => apiRequest<ChatAssessmentCardData>(`${base}/chat-drafts/${id}/publish`, { method: 'POST', signal }),
  preferences: (signal: AbortSignal) => apiRequest<{ auto_add: boolean; revision: number }>(`${base}/preferences`, { signal }),
  savePreferences: (auto_add: boolean, expected_revision: number, signal: AbortSignal) => apiRequest<{ auto_add: boolean; revision: number }>(`${base}/preferences`, { method: 'PATCH', signal, body: JSON.stringify({ auto_add, expected_revision }) }),
  list: (signal: AbortSignal, offset = 0) => apiRequest<{ items: Assessment[]; next_offset: number | null }>(`${base}?offset=${offset}`, { signal }),
  generate: (request: AssessmentGeneration, signal: AbortSignal) => apiRequest<Assessment>(base, { method: 'POST', signal, body: JSON.stringify(request) }),
  detail: (id: string, signal: AbortSignal) => apiRequest<Assessment>(`${base}/${id}`, { signal }),
  attempts: (id: string, signal: AbortSignal) => apiRequest<AssessmentAttempt[]>(`${base}/${id}/attempts`, { signal, cache:'no-store' }),
  start: (id: string, operation: string, signal: AbortSignal) => apiRequest<AssessmentAttempt>(`${base}/${id}/attempts`, { method: 'POST', signal, body: JSON.stringify({ client_request_id: operation }) }),
  attempt: (id: string, signal: AbortSignal) => apiRequest<AssessmentAttempt>(`${base}/attempts/${id}`, { signal }),
  saveDraft: (attempt: AssessmentAttempt, answers: Record<string, string>, signal: AbortSignal) => apiRequest<AssessmentAttempt>(`${base}/attempts/${attempt.id}/draft`, { method: 'PUT', signal, body: JSON.stringify({ expected_revision: attempt.revision, answers }) }),
  submit: (attempt: AssessmentAttempt, answers: Record<string, string>, operation: string, confirmed: boolean, signal: AbortSignal, assistance: 'unknown' | 'independent' | 'assisted' = 'unknown') => apiRequest<AssessmentAttempt>(`${base}/attempts/${attempt.id}/submission`, { method: 'POST', signal, body: JSON.stringify({ expected_revision: attempt.revision, client_request_id: operation, answers, transcription_confirmed: confirmed, assistance }) }),
  paper: async (attempt: AssessmentAttempt, file: File, signal: AbortSignal) => { const stored = await uploadFile(file, file.name, 'assessment', signal); return apiRequest<AssessmentAttempt>(`${base}/attempts/${attempt.id}/source`, { method: 'POST', signal, body: JSON.stringify({ file_id: stored.id, expected_revision: attempt.revision }) }); },
  remove: (id: string, signal: AbortSignal) => apiRequest<void>(`${base}/${id}`, { method: 'DELETE', signal }),
  correct: (attempt: AssessmentAttempt, answers: Record<string,string>, operation: string, confirmed: boolean, signal: AbortSignal, assistance: 'unknown' | 'independent' | 'assisted' = 'unknown') => apiRequest<AssessmentAttempt>(`${base}/attempts/${attempt.id}/corrections`, { method:'POST', signal,body:JSON.stringify({expected_revision:attempt.revision,client_request_id:operation,answers,transcription_confirmed:confirmed,assistance}) }),
};
