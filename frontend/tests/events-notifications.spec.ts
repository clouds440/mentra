import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

test('event editing, reminder inbox and notification preferences', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`agenda_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('an isolated agenda test password');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await page.getByRole('link', { name: 'Events', exact: true }).click();
  await page.getByRole('button', { name: 'New event', exact: true }).click();
  await page.getByLabel('Title', { exact: true }).fill('Revision session');
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  await page.getByLabel('Date', { exact: true }).fill(tomorrow);
  await page.getByLabel('Reminder', { exact: true }).selectOption('disabled');
  await page.getByRole('button', { name: 'Check dates & reminder' }).click();
  await page.getByRole('button', { name: 'Save event', exact: true }).click();
  const detail = page.getByRole('region', { name: 'Event details' });
  await expect(detail.getByRole('heading', { name: 'Revision session' })).toBeVisible();
  await detail.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Title', { exact: true }).fill('Revised session');
  await page.getByRole('button', { name: 'Check dates & reminder' }).click();
  await page.getByRole('button', { name: 'Save event', exact: true }).click();
  await expect(detail.getByRole('heading', { name: 'Revised session' })).toBeVisible();
  await detail.getByRole('button', { name: 'Complete', exact: true }).click();
  await expect(detail.getByRole('button', { name: 'Reopen', exact: true })).toBeVisible();
  await detail.getByRole('button', { name: 'Reopen', exact: true }).click();
  await expect(detail.getByRole('button', { name: 'Complete', exact: true })).toBeVisible();

  const due = new Date(Date.now() + 2000).toISOString();
  const created = await page.request.post('http://127.0.0.1:18003/api/v1/events', {
    headers: { Origin: 'http://127.0.0.1:15173' }, data: {
      title: 'Reminder test', kind: 'quiz', timezone: 'UTC', starts_at: new Date(Date.now() + 3600000).toISOString(),
      reminder: { mode: 'at', at: due }, client_request_id: randomUUID(),
    },
  });
  expect(created.ok()).toBeTruthy();
  await expect.poll(async () => {
    const response = await page.request.get('http://127.0.0.1:18003/api/v1/notifications');
    return (await response.json()).unread_count;
  }).toBe(1);
  await page.getByRole('link', { name: /^Notifications/ }).click();
  await expect(page.getByRole('heading', { name: 'Reminder test' })).toBeVisible();
  await page.getByRole('button', { name: 'Mark read', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Mark read', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'View event', exact: true }).click();
  await expect(detail.getByRole('heading', { name: 'Reminder test' })).toBeVisible();
  await page.goto('/settings?tab=notifications');
  await page.getByLabel('Enable notifications', { exact: true }).uncheck();
  await page.getByRole('button', { name: 'Save settings', exact: true }).click();
  await expect(page.getByText('Settings saved.', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Enable notifications', { exact: true })).not.toBeChecked();
});
