import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

test('typing a new request while an assessment builds changes the primary action to Send', async ({page}) => {
  const fixture = await workspace(page);
  fixture.background();
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('button', {name:'Pause response', exact:true})).toBeEnabled();
  const input = page.getByRole('textbox', {name:'Ask Mentra anything'});
  await input.fill('A new question');
  await expect(page.getByRole('button', {name:'Send message', exact:true})).toBeEnabled();
  await input.fill('');
  await expect(page.getByRole('button', {name:'Pause response', exact:true})).toBeEnabled();
});

for (const mobile of [false, true]) {
  test(`one composer control switches pause/resume/send and restores resume after clearing ${mobile ? 'mobile' : 'desktop'}`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width:390, height:844 });
    await workspace(page, true);
    await page.goto('/chat/polish-chat');
    const composer = page.getByRole('form', { name:'Message Mentra' });
    await composer.getByRole('button', { name:'Pause response', exact:true }).click();
    const resume = composer.getByRole('button', { name:'Resume response', exact:true });
    await expect(resume).toBeEnabled();
    await expect(resume).toHaveAttribute('data-response-action', 'resume');
    const input = composer.getByRole('textbox', { name:'Ask Mentra anything' });
    await input.fill('A new question');
    await expect(composer.getByRole('button', { name:'Send message', exact:true })).toBeEnabled();
    await expect(resume).toHaveCount(0);
    await input.fill('');
    await expect(resume).toBeEnabled();
    await resume.click();
    await expect(composer.getByRole('button', { name:'Pause response', exact:true })).toBeEnabled();
  });
}

test('failed response uses the same control for retry and draft send', async ({ page }) => {
  const fixture = await workspace(page);
  fixture.fail();
  await page.goto('/chat/polish-chat');
  const retry = page.getByRole('button', { name:'Retry response', exact:true });
  await expect(retry).toHaveCount(1);
  await expect(retry).toHaveAttribute('data-response-action', 'retry');
  const input = page.getByRole('textbox', { name:'Ask Mentra anything' });
  await input.fill('Make it shorter');
  await expect(page.getByRole('button', { name:'Send message', exact:true })).toBeEnabled();
  await expect(retry).toHaveCount(0);
  await input.fill('');
  await expect(retry).toBeEnabled();
  const sent = page.waitForRequest(request => request.url().endsWith('/conversations/turns'));
  await retry.click();
  const body = (await sent).postDataJSON();
  expect(body.retry).toBe(true);
  expect(body.client_turn_id).toBe('polish-turn');
  await expect(page.getByRole('button', { name:'Pause response', exact:true })).toBeEnabled();
});
