import { expect, test } from '@playwright/test';
import { richChat } from './renovation-rich-fixtures';

for (const state of ['partial', 'failed', 'completed'] as const) test(`persisted ${state} outcome uses the right feedback`, async ({ page }) => {
  const fixture = await richChat(page, state === 'failed' ? 'The lookup could not be completed.' : 'The completed explanation remains available.');
  const outcome = { version: 3, state, retryable: state !== 'completed', tasks: [] };
  Object.assign(fixture.items[1], { response_outcome: outcome });
  fixture.setTurn({ id: 'outcome-turn', state: 'FAILED', attempt: 1, user_sequence: 1,
    selection: fixture.conversation.selection, error: 'Private provider diagnostic must never render',
    response_outcome: outcome, can_retry: outcome.retryable, can_resume: false });
  await page.goto('/chat/polish-chat');
  const composer = page.locator('.chat-composer-region');
  await expect(page.getByText('Private provider diagnostic must never render')).toHaveCount(0);
  if (state === 'partial') {
    await expect(composer.getByRole('alert')).toHaveCount(0);
    await expect(composer.getByRole('status')).toContainText('Response partly complete');
    await expect(composer.getByRole('status')).toContainText('Your completed results are saved');
    await expect(composer.getByRole('status')).toHaveClass(/text-warning/);
    await expect(page.getByRole('button', { name: 'Retry response' })).toHaveAttribute('title', 'Finish the missing part');
    await expect(page.getByRole('button', { name: 'Retry response' })).toHaveClass(/text-warning/);
  } else if (state === 'failed') {
    await expect(composer.getByRole('alert')).toContainText('Mentra couldn’t finish this response');
    await expect(composer.getByRole('alert')).toHaveClass(/text-danger/);
    await expect(page.getByRole('button', { name: 'Retry response' })).toHaveAttribute('title', 'Retry the failed step');
  } else {
    await expect(composer.getByRole('alert')).toHaveCount(0);
    await expect(composer.getByRole('status')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Retry response' })).toHaveCount(0);
  }
});

test('nonretryable partial preserves its results without suggesting unsafe retries', async ({ page }) => {
  const fixture = await richChat(page, 'The completed result remains available.');
  const outcome = { version: 3, state: 'partial', retryable: false, tasks: [] };
  Object.assign(fixture.items[1], { response_outcome: outcome });
  fixture.setTurn({ id: 'uncertain-turn', state: 'FAILED', attempt: 1, user_sequence: 1,
    selection: fixture.conversation.selection, error: 'An action could not be verified.',
    response_outcome: outcome, can_retry: false, can_resume: false });
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.chat-composer-region').getByRole('status')).toContainText('Your available results are saved');
  await expect(page.getByRole('button', { name: 'Retry response' })).toHaveCount(0);
});
