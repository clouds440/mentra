export function errorMessage(status: number, code: string): string {
  if (code === 'AUTHENTICATION_FAILED') return 'That username or password isn’t correct.';
  if (['USERNAME_TAKEN', 'ACCOUNT_EXISTS'].includes(code)) return 'That username is already registered.';
  if (code.startsWith('SPEECH_')) return 'Your recording could not be transcribed.';
  if (/AI|LLM|PROVIDER|GENERATION/.test(code)) return 'Mentra could not complete your response.';
  if (code === 'NETWORK_ERROR') return 'Couldn’t reach Mentra. Check your connection and try again.';
  if (code === 'REQUEST_TIMEOUT') return 'This took too long to complete.';
  if (code === 'CHAT_NOT_FOUND') return 'Conversation not found.';
  if (['CHAT_ATTEMPT_EXPIRED', 'CHAT_STALE_ATTEMPT'].includes(code)) return 'This response is no longer running. Check the saved conversation before retrying.';
  if (code === 'CHAT_DELETED') return 'This conversation was deleted.';
  if (code === 'MEMORY_CAPACITY') return 'Memory capacity reached. Delete unused memories first.';
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
