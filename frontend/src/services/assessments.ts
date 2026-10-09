import { apiRequest } from './api';
import type { Assessment, AssessmentAttempt, AssessmentGeneration } from '../types/assessments';
const base = '/api/v1/assessments';
export const assessments = {
  list: (signal: AbortSignal, offset = 0) => apiRequest<{ items: Assessment[]; next_offset: number | null }>(`${base}?offset=${offset}`, { signal }),
  generate: (request: AssessmentGeneration, signal: AbortSignal) => apiRequest<Assessment>(base, { method: 'POST', signal, body: JSON.stringify(request) }),
  detail: (id: string, signal: AbortSignal) => apiRequest<Assessment>(`${base}/${id}`, { signal }),
  attempts: (id: string, signal: AbortSignal) => apiRequest<AssessmentAttempt[]>(`${base}/${id}/attempts`, { signal }),
  start: (id: string, operation: string, signal: AbortSignal) => apiRequest<AssessmentAttempt>(`${base}/${id}/attempts`, { method: 'POST', signal, body: JSON.stringify({ client_request_id: operation }) }),
  attempt: (id: string, signal: AbortSignal) => apiRequest<AssessmentAttempt>(`${base}/attempts/${id}`, { signal }),
  submit: (attempt: AssessmentAttempt, answers: Record<string, string>, operation: string, confirmed: boolean, signal: AbortSignal) => apiRequest<AssessmentAttempt>(`${base}/attempts/${attempt.id}/submission`, { method: 'POST', signal, body: JSON.stringify({ expected_revision: attempt.revision, client_request_id: operation, answers, transcription_confirmed: confirmed }) }),
  paper: (attempt: AssessmentAttempt, file: File, signal: AbortSignal) => { const body = new FormData(); body.append('file', file); body.append('expected_revision', String(attempt.revision)); return apiRequest<AssessmentAttempt>(`${base}/attempts/${attempt.id}/source`, { method: 'POST', signal, body }); },
  remove: (id: string, signal: AbortSignal) => apiRequest<void>(`${base}/${id}`, { method: 'DELETE', signal }),
  correct: (attempt: AssessmentAttempt, answers: Record<string,string>, operation: string, confirmed: boolean, signal: AbortSignal) => apiRequest<AssessmentAttempt>(`${base}/attempts/${attempt.id}/corrections`, { method:'POST', signal,body:JSON.stringify({expected_revision:attempt.revision,client_request_id:operation,answers,transcription_confirmed:confirmed}) }),
};
