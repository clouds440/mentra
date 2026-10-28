import { test, expect, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { chooseOption } from './select-helpers';

async function profilePage(page: Page, legacy = false) {
  await workspace(page);
  let profile = { learner_id: 'polish-user', details: { education_level: 'college', field_of_study: 'Physics', learning_goal: 'Understand motion', learning_preference: legacy ? 'concise' : 'balanced', explanation_depth: legacy ? 'deep' : 'standard' },
    estimates: Object.fromEntries(['overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity'].map(key => [key, { value: null, confidence: 0, evidence_count: 0 }])),
    onboarding_phase: 'complete', calibration_status: 'completed', evaluation_status: 'applied', version: 1, context_version: 1 };
  const saved: Record<string, unknown>[] = [];
  let conflict = false;
  await page.route('**/api/v1/student-profile', route => route.fulfill({ json: profile }));
  await page.route('**/api/v1/student-profile/details', async route => {
    const request = route.request().postDataJSON();
    if (conflict) return route.fulfill({ status: 409, json: { error: { code: 'profile_conflict', message: 'Profile changed elsewhere' } } });
    saved.push(request.details); profile = { ...profile, details: request.details, version: profile.version + 1 };
    await route.fulfill({ json: profile });
  });
  await page.goto('/settings'); await page.getByRole('button', { name: 'Edit profile', exact: true }).click();
  return { saved, conflict: () => { conflict = true; profile = { ...profile, version: profile.version + 1 }; } };
}

for (const width of [375, 1280]) test(`teaching defaults combine, preview locally and persist at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 850 });
  const { saved } = await profilePage(page);
  await chooseOption(page.getByLabel('Teaching approach', { exact: true }), 'examples_first');
  await chooseOption(page.getByLabel('Participation', { exact: true }), 'interactive');
  await chooseOption(page.getByLabel('Visual support', { exact: true }), 'prefer_visuals');
  await chooseOption(page.getByLabel('Explanation detail', { exact: true }), 'deep');
  await chooseOption(page.getByLabel('Learning purpose', { exact: true }), 'apply');
  const preview = page.getByRole('region', { name: 'Preference preview' });
  await expect(preview).toContainText('Put 3'); await expect(preview).toContainText('f(x) = 2x');
  await expect(preview.getByRole('img')).toBeVisible();
  await preview.getByRole('button', { name: '10', exact: true }).click(); await expect(preview.getByRole('status')).toContainText('not recorded');
  expect(saved).toHaveLength(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  expect(saved[0]).toMatchObject({ learning_preference: 'examples_first', participation: 'interactive', visual_support: 'prefer_visuals', explanation_depth: 'deep', learning_purpose: 'apply' });
  await page.reload(); await expect(page.getByText('Interactive', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit profile', exact: true }).click();
  await chooseOption(page.getByLabel('Participation', { exact: true }), 'mostly_explanations');
  await chooseOption(page.getByLabel('Visual support', { exact: true }), 'mostly_text');
  await expect(page.getByRole('region', { name: 'Preference preview' }).getByRole('button')).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Preference preview' }).getByRole('img')).toHaveCount(0);
});

test('legacy concise maps to brief and can explicitly switch to detailed', async ({ page }) => {
  const { saved } = await profilePage(page, true);
  await expect(page.getByLabel('Teaching approach', { exact: true }).and(page.getByRole('combobox'))).toContainText('Adaptive');
  await expect(page.getByLabel('Explanation detail', { exact: true }).and(page.getByRole('combobox'))).toContainText('Brief');
  await chooseOption(page.getByLabel('Explanation detail', { exact: true }), 'deep');
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  expect(saved[0]).toMatchObject({ learning_preference: 'balanced', explanation_depth: 'deep', participation: 'adaptive', visual_support: 'adaptive' });
});

test('conflict preserves preference draft until explicit reload', async ({ page }) => {
  const state = await profilePage(page);
  await chooseOption(page.getByLabel('Participation', { exact: true }), 'interactive'); state.conflict();
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByText('Your profile changed elsewhere.', { exact: false })).toBeVisible();
  await expect(page.getByLabel('Participation', { exact: true }).and(page.getByRole('combobox'))).toContainText('Interactive');
  await page.getByRole('button', { name: 'Reload latest profile', exact: true }).click();
  await expect(page.getByLabel('Participation', { exact: true }).and(page.getByRole('combobox'))).toContainText('Adaptive');
});
