export const responseError = 'Mentra couldn’t finish this response. Please try again.';

// Persisted errors arrive in successful responses and bypass ApiError. Only
// explicitly approved text may render; unknown/legacy diagnostics stay private.
export function chatErrorMessage(message?: string | null): string {
  if (message === 'The requested document could not be found. Select another document.') return message;
  if (message === 'Generation interrupted. Retry this message.') return 'This response was interrupted. Please try again.';
  return responseError;
}

export function toolWarningMessage(tool: string, code: string): string {
  if (/CONFIRM|REVIEW_REQUIRED/.test(code)) return 'Please review this action before continuing.';
  if (tool === 'web_search') return 'Web search couldn’t be completed. Some information may be missing.';
  if (tool === 'event_manage') return 'The event change couldn’t be confirmed. Check your events before trying again.';
  if (tool === 'event_lookup') return 'Your events couldn’t be checked.';
  if (tool.startsWith('assessment_')) return 'This practice step couldn’t be completed. Check your practice before trying again.';
  if (['search_study_material', 'get_study_source_chunk', 'document_extract'].includes(tool)) {
    if (/BUDGET|LIMIT/.test(code)) return 'Additional material checks reached the limit for this response. The answer uses the information that was available.';
    if (code === 'TOOL_TIMEOUT') return 'A study-material lookup took too long. Some passages may not have been checked.';
    if (tool === 'document_extract') return 'An attached file couldn’t be read. Check the original file.';
    return 'Some source passages couldn’t be retrieved. Other retrieved passages may still support this answer.';
  }
  if (tool === 'user_memory' || tool === 'history_lookup') return 'Some information from previous conversations couldn’t be checked.';
  return 'Part of this request couldn’t be completed. Some information may be missing.';
}

export function materialWarningMessage(message: string): string {
  const page = /(?:page|slide) (\d+)/i.exec(message);
  const location = page ? ` on ${/slide/i.test(message) ? 'slide' : 'page'} ${page[1]}` : '';
  if (/OCR|handwriting|equations/i.test(message)) return `Some text${location} may be inaccurate or missing. Check handwriting and equations against the original.`;
  if (/no readable|could not be read|could not be decoded|could not be located/i.test(message)) return `Some content${location} couldn’t be read. Check the original file.`;
  if (/not fetched|external.*scripts/i.test(message)) return 'Content linked from another location wasn’t included. Check the original file.';
  if (/headers|footers|speaker notes|annotations|charts|drawing text/i.test(message)) return 'Some notes, images or other content may be missing. Check the original file.';
  if (/ambiguous|No answer was recognized|review every answer/i.test(message)) return 'Some answers or question numbers couldn’t be read clearly. Review every answer before submitting.';
  return 'Some content may be incomplete. Check the original file.';
}

export function errorMessage(status: number, code: string): string {
  if (code === 'FILES_SIZE') return 'This file exceeds the upload size limit.';
  if (code === 'FILES_EMPTY') return 'Choose a non-empty file.';
  if (code === 'FILES_FORMAT') return 'This file format could not be read. Choose a supported file.';
  if (code === 'FILES_NOT_FOUND') return 'This file is no longer available. Upload it again to continue.';
  if (code === 'FILES_UNAVAILABLE') return 'File storage is temporarily unavailable. Please retry.';
  if (code === 'FILES_PENDING') return 'This upload is still processing. Retry shortly.';
  if (code === 'FILES_CAPACITY') return 'Finish or remove pending uploads before adding more files.';
  if (code === 'FILES_BUSY') return 'File transfer capacity is busy. Please retry shortly.';
  if (code === 'FILES_INTEGRITY') return 'This file could not be verified. Please retry the upload.';
  if (code === 'CHAT_SEARCH_BUSY') return 'This search took too long. Try a more specific phrase.';
  if (code === 'CHAT_SEARCH_QUERY_INVALID') return 'Use a search phrase of at most 200 characters.';
  if (code === 'ASSESSMENT_PRACTICE_DELETED') return 'This follow-up was deleted. Refresh the results before choosing new practice.';
  if (code === 'AUTHENTICATION_FAILED') return 'That username or password isn’t correct.';
  if (code === 'PASSWORD_CHANGE_FAILED') return 'Your current password is incorrect.';
  if (['USERNAME_TAKEN', 'ACCOUNT_EXISTS'].includes(code)) return 'That username is already registered.';
  if (code.startsWith('SPEECH_')) return 'Your recording could not be transcribed.';
  if (code === 'AI_CONFIGURATION_ERROR') return 'Mentra isn’t available right now. Please try again later.';
  if (/^(AI_|LLM_|PROVIDER_|GENERATION_)/.test(code)) return responseError;
  if (code === 'NETWORK_ERROR') return 'Couldn’t reach Mentra. Check your connection and try again.';
  if (code === 'REQUEST_TIMEOUT') return 'This took too long to complete.';
  if (code === 'CHAT_NOT_FOUND') return 'Conversation not found.';
  if (['CHAT_ATTEMPT_EXPIRED', 'CHAT_STALE_ATTEMPT'].includes(code)) return 'This response is no longer running. Check the saved conversation before retrying.';
  if (code === 'CHAT_DELETED') return 'This conversation was deleted.';
  if (code === 'MEMORY_CAPACITY') return 'Memory capacity reached. Delete unused memories first.';
  if (code === 'ASSESSMENT_TARGET_UNAVAILABLE') return 'A selected topic is no longer available in this learning context. Return to Progress and choose another topic.';
  if (code === 'ASSESSMENT_PRACTICE_INVALID') return 'Choose incorrect or partially correct questions from the current results.';
  if (code === 'ASSESSMENT_CAPACITY') return 'Assessment capacity reached. Your saved results are preserved.';
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
