import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

const origin = 'http://127.0.0.1:18003';
test('custom topic and forms persist through real chat; static bars use structured tool data', async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`rich_${randomUUID().slice(0,8)}`);
  await page.getByLabel('Password', { exact: true }).fill('isolated rich interaction password');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  const composer = page.getByRole('textbox', { name: 'Ask Mentra anything' });
  async function send(text: string) {
    await expect(composer).toBeEnabled(); await composer.fill(text);
    await page.getByRole('button', { name: 'Send message' }).click();
    await expect(composer).toBeEnabled({ timeout: 20000 });
  }
  await send('Show topic choices with custom input');
  const choice = page.getByRole('region', { name: 'Interactive question' });
  await choice.getByRole('radio', { name: "I'll write my own topic" }).check();
  await choice.getByRole('textbox', { name: 'Your topic' }).fill('Database indexes');
  await choice.getByRole('button', { name: 'Submit selection' }).click();
  await expect(page.getByText('Received your input: custom: Database indexes', { exact: true })).toBeVisible({ timeout: 20000 });
  await page.reload();
  await expect(choice.getByRole('textbox', { name: 'Your topic' })).toHaveValue('Database indexes');
  await expect(choice.getByRole('textbox', { name: 'Your topic' })).toBeDisabled();
  await send('Show study setup form');
  const form = page.getByRole('region', { name: 'Interactive form' });
  await form.getByLabel('Topic', { exact: true }).fill('Indexes');
  await form.getByLabel('Minutes', { exact: true }).fill('20');
  await form.getByRole('button', { name: 'Submit answer' }).click();
  await expect(page.getByText('Received your input: topic: Indexes; minutes: 20', { exact: true })).toBeVisible({ timeout: 20000 });
  await send('Show concept difficulty bars');
  await expect(page.getByRole('meter', { name: 'Concept A' })).toHaveAttribute('aria-valuenow', '3');
  await expect(page.getByText('3 / 5 points · 60%')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('meter', { name: 'Concept B' })).toHaveAttribute('aria-valuenow', '4');
});

test('native choices continue chat and retain selections after refresh on mobile', async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`choices_${randomUUID().slice(0,8)}`);
  await page.getByLabel('Password', { exact: true }).fill('isolated interactive password');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  const composer = page.getByRole('textbox', { name: 'Ask Mentra anything' });
  async function send(text: string) {
    await expect(composer).toBeEnabled(); await composer.fill(text);
    await page.getByRole('button', { name: 'Send message' }).click();
    await expect(composer).toBeEnabled();
  }
  await send('Show single choices');
  const cards = page.getByRole('region', { name: 'Interactive question' });
  await expect(cards).toHaveCount(1);
  await cards.first().getByRole('radio', { name: 'Biology' }).focus();
  await page.keyboard.press('Space');
  await cards.first().getByRole('button', { name: 'Submit selection' }).click();
  await expect(page.getByText('Selected topic IDs: biology', { exact: true })).toBeVisible();
  await expect(cards.first().getByRole('radio', { name: 'Biology' })).toBeDisabled();
  await send('Show multiple choices');
  await expect(cards).toHaveCount(2);
  await cards.last().getByRole('checkbox', { name: 'Algebra' }).check();
  await cards.last().getByRole('checkbox', { name: 'Physics' }).check();
  await cards.last().getByRole('button', { name: 'Submit selection' }).click();
  await expect(page.getByText('Selected topic IDs: algebra, physics', { exact: true })).toBeVisible();
  await page.reload();
  await expect(cards).toHaveCount(2);
  await expect(cards.first().getByRole('radio', { name: 'Biology' })).toBeChecked();
  await expect(cards.last().getByRole('checkbox', { name: 'Physics' })).toBeChecked();
  await expect(cards.last().getByRole('checkbox', { name: 'Physics' })).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('choices-mobile.png'), fullPage: true });
  await send('Hello'); await expect(composer).toBeEnabled();
});

test('first chat generates an interactive assessment from a topic with no prior learner data', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('Username', { exact:true }).fill(`cold_quiz_${randomUUID().slice(0,8)}`);
  await page.getByLabel('Password', { exact:true }).fill('isolated cold start password');
  await page.getByRole('button', { name:'Create account', exact:true }).click();
  await finishOnboardingWithoutAssessment(page);
  expect((await (await page.request.get(`${origin}/api/v1/assessments`)).json()).items).toHaveLength(0);
  await page.getByRole('textbox', { name:'Ask Mentra anything' }).fill('Give me an interactive assessment on introductory optics');
  await page.getByRole('button', { name:'Send message' }).click();
  const card = page.getByRole('region', { name:'Chat assessment' });
  const quiz = card.getByRole('region', { name:'Interactive quiz' });
  await expect(quiz.getByText(/Question 1 of 3/)).toBeVisible({ timeout:20_000 });
  await expect(page.getByLabel('Response limitations')).toHaveCount(0);
  await quiz.getByRole('radio', { name:'A supported explanation.', exact:true }).check();
  await quiz.getByRole('button', { name:'Next' }).click();
  await expect(quiz.getByText(/Question 2 of 3/)).toBeVisible();
  await page.reload();
  await expect(quiz.getByText(/Question 1 of 3/)).toBeVisible();
  await expect(quiz.getByRole('radio').first()).not.toBeChecked();
});

for (const request of ['Give me a five question interactive quiz on Linear equations', 'Quiz me with five clickable options questions on Linear equations', 'I keep mixing up linear equations']) {
test(`five question MCQ invoked from ${request} restores progress and grades`, async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`mcq_${randomUUID().slice(0,8)}`);
  await page.getByLabel('Password', { exact: true }).fill('isolated interactive password');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  const headers = { Origin: 'http://127.0.0.1:15173' };
  const context = await (await page.request.post(`${origin}/api/v1/learning-contexts`, { headers, data: { name: 'Algebra', activate: true } })).json();
  const setup = await page.request.post(`${origin}/api/v1/assessments`, { headers, data: { client_request_id: randomUUID(), context_id: context.context_id, topic: 'Linear equations', concept_names: ['Linear equations'], confirm_new_concepts: true, count: 1 } });
  expect(setup.ok()).toBeTruthy();
  await page.request.delete(`${origin}/api/v1/assessments/${(await setup.json()).id}`, { headers });
  const composer = page.getByRole('textbox', { name: 'Ask Mentra anything' });
  await composer.fill(request);
  await page.getByRole('button', { name: 'Send message' }).click();
  const card = page.getByRole('region', { name: 'Chat assessment' });
  await expect(card).toBeVisible();
  await expect(card.getByRole('button', { name: 'Add & answer', exact: true })).toHaveCount(0);
  const savedAssessments=(await (await page.request.get(`${origin}/api/v1/assessments`)).json()).items;
  expect(savedAssessments).toHaveLength(1);
  expect(savedAssessments[0].questions).toHaveLength(5);
  expect(JSON.stringify(savedAssessments[0])).not.toContain('correct_option_id');
  const quiz = card.getByRole('region', { name: 'Interactive quiz' });
  await expect(quiz.getByRole('radio').first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('interactive-desktop-light.png'), fullPage: true });
  await quiz.getByRole('radio', { name: 'A supported explanation.', exact: true }).check();
  await quiz.getByRole('button', { name: 'Next', exact:true }).click();
  await expect(quiz.getByText(/Question 2 of 5/)).toBeVisible();
  expect(await (await page.request.get(`${origin}/api/v1/assessments/${savedAssessments[0].id}/attempts`)).json()).toHaveLength(0);
  const chatPath = new URL(page.url()).pathname;
  await page.getByRole('button', { name:'Start a new chat' }).click();
  await expect(page.getByRole('link', { name: 'Chat', exact: true })).toHaveAttribute('href', '/');
  await page.getByRole('region', { name: 'Conversation history' }).locator(`a[href="${chatPath}"]`).click();
  await expect(quiz.getByText(/Question 2 of 5/)).toBeVisible();
  await page.setViewportSize({ width:390, height:844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({path:testInfo.outputPath('interactive-mobile.png')});
  await page.setViewportSize({width:1280,height:1000});
  for(let i=2;i<=5;i++) {
    await quiz.getByRole('radio', {name:i<=3 ? 'A supported explanation.' : 'An unsupported explanation.', exact:true}).check();
    if(i<5) await quiz.getByRole('button', {name:'Next',exact:true}).click();
  }
  await quiz.getByLabel('Quiz assistance used').click();
  await page.getByRole('option', { name:'I answered independently',exact:true }).click();
  // All answers commit together; a lost response recovers the canonical submission.
  if(request.startsWith('Give me')) await page.route('**/api/v1/assessments/attempts/*/submission', async route => {
    await route.fetch(); await route.abort('failed');
  }, {times:1});
  await quiz.getByRole('button',{name:'Submit',exact:true}).click();
  await expect(card.getByText('Final result: 6/10', { exact: true })).toBeVisible({ timeout: 20000 });
  await expect.poll(async () => {
    const attempts = await (await page.request.get(`${origin}/api/v1/assessments/${savedAssessments[0].id}/attempts`)).json();
    return attempts[0]?.evidence_status;
  }).toBe('applied');
  const feedback = card.getByRole('region', { name: 'Assessment feedback' });
  await feedback.getByRole('button', { name: 'List view', exact: true }).click();
  await expect(feedback.getByText('3 correct', { exact:true })).toBeVisible();
  await expect(feedback.getByText('2 incorrect', { exact:true })).toBeVisible();
  await expect(feedback.getByRole('region', { name: 'Question 4 feedback' })).toContainText('An unsupported explanation.');
  await expect(feedback.getByRole('region', { name: 'Question 4 feedback' })).toContainText('Correct answer');
  await feedback.getByRole('heading', { name:'Your results' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('feedback-desktop-dark.png') });
  await page.evaluate(() => localStorage.setItem('mentra-theme', 'light'));
  await page.reload();
  await expect(card.getByText('Final result: 6/10', { exact: true })).toBeVisible();
  await feedback.getByRole('button', { name: 'List view', exact: true }).click();
  await feedback.getByRole('heading', { name:'Your results' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('feedback-desktop-light.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await feedback.getByRole('heading', { name:'Your results' }).scrollIntoViewIfNeeded();
  await expect.poll(() => page.getByRole('complementary', { name:'Main navigation' }).evaluate(element => element.getBoundingClientRect().right)).toBeLessThanOrEqual(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('feedback-mobile-light.png') });
  await feedback.getByRole('region', { name:'Question 4 feedback' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('feedback-incorrect-mobile.png') });
});

}
