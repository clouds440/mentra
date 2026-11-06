import { test, expect } from '@playwright/test';
import { assessmentFixture as fixture } from './fixtures/assessment';

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

test('an incomplete current handoff fails visibly without issuing hydration or history fallbacks', async ({ page }) => {
  const state = await fixture(page, { incomplete: true });
  await expect(page.getByRole('alert')).toContainText('handoff is incomplete');
  await expect(state.quiz).toHaveCount(0);
  expect(state.reads.filter(path=>path.includes('/chat-drafts/')||path.endsWith('/handoff-quiz/attempts'))).toEqual([]);
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
