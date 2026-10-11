export function errorMessage(status: number, code: string): string {
  if (code === 'AUTHENTICATION_FAILED') return 'That username or password isn’t correct.';
  if (['USERNAME_TAKEN', 'ACCOUNT_EXISTS'].includes(code)) return 'That username is already taken.';
  if (code.startsWith('SPEECH_')) return 'Your recording could not be transcribed.';
  if (/AI|LLM|PROVIDER|GENERATION/.test(code)) return 'Mentra could not complete your response.';
  if (code === 'NETWORK_ERROR') return 'Mentra could not be reached.';
  if (code === 'REQUEST_TIMEOUT') return 'This took too long to complete.';
  if (status === 401) return 'Your session has ended.';
  if (status === 403) return 'This is unavailable to your account.';
  if (status === 404) return 'This is no longer available.';
  if (status === 409) return 'This changed before your update could be saved.';
  if (status === 413) return 'This file is too large.';
  if (status === 415) return 'This file type is not supported.';
  if (status === 429) return 'Mentra is busy right now.';
  if (status === 400 || status === 422) return 'These details could not be accepted.';
  return 'Mentra could not complete this request.';
}
