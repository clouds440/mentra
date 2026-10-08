import { apiRequest, ApiError } from './api';
import type { CalibrationAttempt, ProfileDetails, StudentProfile } from '../types/studentProfile';

async function request<T>(path = '', init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  init.signal?.addEventListener('abort', cancel, { once: true });
  if (init.signal?.aborted) cancel();
  const timer = window.setTimeout(cancel, 60_000);
  try {
    return await apiRequest<T>(`/api/v1/student-profile${path}`, { ...init, signal: controller.signal, cache: 'no-store' });
  } finally {
    window.clearTimeout(timer);
    init.signal?.removeEventListener('abort', cancel);
  }
}
export const getProfile = (signal?: AbortSignal) => request<StudentProfile>('', { signal });
export const updateDetails = (details: ProfileDetails, version: number) => request<StudentProfile>('/details', {
  method: 'PUT', body: JSON.stringify({ details, expected_version: version }),
});
export const getCalibration = (signal?: AbortSignal) => request<CalibrationAttempt | null>('/calibration', { signal });
export const startCalibration = () => request<CalibrationAttempt>('/calibration', { method: 'POST' });
export const completeCalibration = (attempt: CalibrationAttempt, answers: Record<string, string>) => request<{ profile: StudentProfile; evidence_id: string }>(`/calibration/${attempt.id}/complete`, {
  method: 'POST', body: JSON.stringify({ expected_version: attempt.version, answers }),
});
export const skipCalibration = (version: number) => request<StudentProfile>('/calibration/skip', {
  method: 'POST', body: JSON.stringify({ expected_version: version }),
});
export const retryEvaluation = () => request<StudentProfile>('/calibration/evaluate', { method: 'POST' });
export function profileError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status >= 500) return 'Mentra couldn’t save your profile right now. Please try again.';
    if (error.status === 422) return 'Check the highlighted details and try again.';
    return error.message;
  }
  return 'Couldn’t reach Mentra. Your saved progress is safe. Check your connection and try again.';
}
