import { test, expect, type Page } from '@playwright/test';
import type { AssessmentAttempt } from '../src/types/assessments';

async function fixture(page: Page, { delay = 4000, duplicate = false, legacy = false } = {}) {
  const date = '2026-11-05T00:00:00Z', selection = { mode: 'STANDARD' };
  const conversation = { id: 'handoff-chat', title: 'Handoff chat', revision: 3, message_count: 2, selection, created_at: date, updated_at: date, deleted_at: null };
  const assessment = { id: 'handoff-quiz', context_id: 'physics', title: 'Net force', purpose: 'practice', revision: 1, sources: [], created_at: date,
    preferences: { delivery: 'interactive' }, questions: Array.from({ length: 3 }, (_, index) => ({ id: `q-${index}`, prompt: `A 4 kg block has a net force of 6 N. What is its acceleration? (${index + 1})`, concept_ids: ['force'], marks: 2, difficulty: .3, source_tokens: [], options: [{ id: 'a', label: '1.5 m/s²' }, { id: 'b', label: '24 m/s²' }] })) };
  const card = { id: 'handoff-draft', conversation_id: conversation.id, assessment_id: assessment.id, assessment };
  const generation = { id: 'handoff-card', generation_job_id: 'handoff-job', title: assessment.title };
  const items = [{ id: 'question', conversation_id: conversation.id, sequence: 1, role: 'user', content: 'Give me a quiz.', created_at: date },
    { id: 'reply', conversation_id: conversation.id, sequence: 2, role: 'assistant', content: 'Your quiz is ready.', assessment_cards: [generation], created_at: date },
    ...(duplicate ? [{ id: 'duplicate-preview', conversation_id: conversation.id, sequence: 3, role: 'assistant', content: 'The same saved work.', assessment_cards: [{ ...generation, id: 'another-card' }], created_at: date }] : [])];
  const reads: string[] = []; let completedAt = 0, incomingAttempt: AssessmentAttempt | null = null;
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname; reads.push(path);
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = { learner_id: 'handoff-user', username: 'handoff-user', user_id: null, provider: null };
    else if (path.endsWith('/student-profile')) body = { learner_id: 'handoff-user', details: { education_level: 'college', field_of_study: 'Physics', learning_goal: 'Learn', learning_preference: 'balanced', explanation_depth: 'standard' }, estimates: Object.fromEntries(['overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity'].map(key => [key, { value: null, confidence: 0, evidence_count: 0 }])), onboarding_phase: 'complete', calibration_status: 'skipped', evaluation_status: 'not_started', version: 1, context_version: 1 };
    else if (path.endsWith('/conversations/sync')) body = { reset: false, cursor: 3, has_more: false, conversations: [conversation], deleted_ids: [], list_cursor: null };
    else if (path.endsWith('/status')) body = { conversation, items, has_more: false, next_cursor: null, turn: { id: 'handoff-turn', state: 'SUCCEEDED', attempt: 1, user_sequence: 1, selection, error: null } };
    else if (path.endsWith('/generation-jobs/handoff-job')) {
      completedAt = Date.now();
      body = { id: 'handoff-job', state: 'completed', title: assessment.title, conversation_id: conversation.id,
        completed_parts: 3, total_parts: 3, result: card, can_retry: false, revision: 3,
        ...(!legacy ? { hydration: { version: 1, attempt: incomingAttempt } } : {}) };
    } else if (path.endsWith('/chat-drafts/handoff-draft')) {
      await new Promise(resolve => setTimeout(resolve, delay)); body = card;
    } else if (path.endsWith('/handoff-quiz/attempts')) {
      await new Promise(resolve => setTimeout(resolve, delay)); body = [];
    } else if (path.endsWith('/notifications/unread-count')) body = { count: 0 };
    else if (path.endsWith('/assessments/preferences')) body = { auto_add: false, revision: 1 };
    await route.fulfill({ json: body });
  });
  await page.goto('/chat/handoff-chat');
  return { reads, completedAt: () => completedAt, quiz: page.getByRole('region', { name: 'Interactive quiz' }),
    completeElsewhere() {
      incomingAttempt = { id: 'external-attempt', assessment_id: assessment.id, revision: 2, state: 'graded', attempt_number: 1,
        answers: { 'q-0': 'a', 'q-1': 'a', 'q-2': 'a' }, grades: [], extraction: null, error: null,
        evidence_status: 'applied', created_at: date, grade_revision: 1, grade_history: [] };
    } };
}

test('a complete handoff paints immediately and cannot lose choices to delayed redundant reads', async ({ page }, info) => {
  const state = await fixture(page);
  await expect(state.quiz.getByRole('radio', { name: '1.5 m/s²', exact: true })).toBeVisible();
  const elapsed = Date.now() - state.completedAt();
  await state.quiz.getByRole('radio').first().check();
  await state.quiz.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(state.quiz.getByText(/Question 2 of 3/)).toBeVisible();
  await page.waitForTimeout(4200);
  await state.quiz.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(state.quiz.getByRole('radio').first()).toBeChecked();
  expect(state.reads.filter(path => path.includes('/chat-drafts/') || path.endsWith('/handoff-quiz/attempts'))).toEqual([]);
  expect(state.reads.filter(path => path.endsWith('/generation-jobs/handoff-job'))).toHaveLength(1);
  expect(elapsed).toBeLessThan(1000);
  console.log('ASSESSMENT_HANDOFF_METRIC', JSON.stringify({ ready_to_usable_ms: elapsed, blocking_reads: 0 }));
  await info.attach('handoff-timing', { body: JSON.stringify({ ready_to_usable_ms: elapsed }), contentType: 'application/json' });
});

test('two cards share one job read and keep independent local navigation', async ({ page }) => {
  const state = await fixture(page, { duplicate: true });
  await expect(state.quiz).toHaveCount(2);
  await expect(state.quiz.first().getByRole('radio').first()).toBeVisible();
  await state.quiz.first().getByRole('radio').first().check();
  await state.quiz.first().getByRole('button', { name: 'Next', exact: true }).click();
  await expect(state.quiz.first().getByText(/Question 2 of 3/)).toBeVisible();
  await expect(state.quiz.last().getByText(/Question 1 of 3/)).toBeVisible();
  expect(state.reads.filter(path => path.endsWith('/generation-jobs/handoff-job'))).toHaveLength(1);
});

test('legacy completed jobs retain the authoritative history fallback', async ({ page }) => {
  const state = await fixture(page, { legacy: true, delay: 100 });
  await expect(state.quiz.getByRole('radio').first()).toBeVisible();
  expect(state.reads.some(path => path.endsWith('/chat-drafts/handoff-draft'))).toBeTruthy();
  expect(state.reads.some(path => path.endsWith('/handoff-quiz/attempts'))).toBeTruthy();
});

test('a focus refresh cannot overwrite dirty local answers with another session result', async ({ page }) => {
  const state = await fixture(page);
  const choice = state.quiz.getByRole('radio').first();
  await expect(choice).toBeVisible(); await choice.check();
  state.completeElsewhere();
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('alert')).toContainText('Your answers are kept');
  await expect(choice).toBeChecked(); await expect(choice).toBeDisabled();
  await expect(state.quiz.getByText(/Question 1 of 3/)).toBeVisible();
});
