import { test, expect } from '@playwright/test';
import { errorMessage, chatErrorMessage, materialWarningMessage, toolWarningMessage } from '../src/services/userError';

test('HTTP failures ignore private server messages while preserving account guidance', () => {
  const diagnostic = 'SQLAlchemy AI_API_KEY provider internal trace';
  for (const status of [400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 502, 503]) {
    expect(errorMessage(status, 'HTTP_ERROR')).not.toContain(diagnostic);
  }
  expect(errorMessage(401, 'AUTHENTICATION_FAILED')).toContain('username or password');
  expect(errorMessage(409, 'ACCOUNT_EXISTS')).toContain('already registered');
});

test('unknown saved errors and file notes use safe fallbacks with useful locations', () => {
  const diagnostic = 'SQLAlchemy provider internal_trace at private host';
  expect(chatErrorMessage(diagnostic)).toContain('Please try again');
  expect(materialWarningMessage(diagnostic)).toBe('Some content may be incomplete. Check the original file.');
  expect(materialWarningMessage('Page 12 has no readable native text and OCR is unavailable; check the original.')).toContain('on page 12');
  expect(materialWarningMessage('OCR engine private trace on slide 3')).not.toContain('OCR');
  expect(toolWarningMessage('unknown_internal_tool', 'TOOL_INVALID_ARGUMENTS')).not.toContain('tool');
  expect(toolWarningMessage('event_manage', 'TOOL_TIMEOUT')).toContain('Check your events before trying again');
});
