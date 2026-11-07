import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { workspace } from './renovation-fixtures';
import { chooseOption } from './select-helpers';

async function pageWorkspace(page: Page) {
  await workspace(page, false, true);
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { learner_id: 'polish-user', username: 'learner', user_id: 'design-account', provider: null } }));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/v1/documents/material-1', route => route.fulfill({ json: {
    id: 'material-1', title: 'Motion and forces', filename: 'Physics notes.pdf', context_ids: ['context-1'],
    archived: false, revision: 1, active_generation_id: 'generation-1', version_count: 1, jobs: [],
    versions: [{ id: 'version-1', filename: 'Physics notes.pdf', media_type: 'application/pdf', size_bytes: 10240, extraction_state: 'ready', generation_id: 'generation-1' }],
    generations: [{ id: 'generation-1', version_id: 'version-1', state: 'READY', warnings: [], chunk_count: 4 }],
  } }));
}

const routes = ['/library', '/library/new', '/library/material-1', '/progress', '/progress?tab=events', '/assessments', '/assessments?tab=create', '/assessments?tab=mistakes', '/settings', '/settings?tab=memories', '/settings?tab=notifications', '/notifications'];
for (const width of [390, 1440]) test(`every page keeps the side-panel toggle usable without sources at ${width}px`, async ({ page }, info) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width, height: 1000 });
  await pageWorkspace(page);
  for (const [index, route] of ['/', ...routes].entries()) {
    await page.goto(route);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const toggle = page.getByRole('button', { name: 'Open side panel', exact: true });
    await expect(toggle).toBeInViewport();
    await toggle.click();
    await expect(page.getByRole('heading', { name: 'Your sources, beside your work' })).toBeVisible();
    const close = page.getByRole('button', { name: 'Hide side panel', exact: true });
    await expect(close).toBeInViewport();
    if (route === '/library') {
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(result.violations.map(item => item.id)).toEqual([]);
      await page.screenshot({ path: info.outputPath(`library-panel-${width}.png`) });
    }
    await close.click();
    await expect(toggle).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), route).toBe(true);
    if (route !== '/') {
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: info.outputPath(`page-${index}-${width}.png`) });
    }
  }
});

for (const width of [390, 1440]) test(`Library views preserve filtering and every source action at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await pageWorkspace(page);
  await page.goto('/library');
  for (const name of ['List view', 'Grid view', 'List view']) {
    await page.getByRole('button', { name, exact: true }).click();
    await expect(page.getByRole('button', { name: 'Add material', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Motion and forces', exact: true })).toBeVisible();
    for (const action of ['Manage material', 'Study in chat', 'Quiz this material']) await expect(page.getByRole('link', { name: action, exact: true })).toBeVisible();
    expect(await page.locator('.workspace-page').evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  }
  await chooseOption(page.getByRole('combobox', { name: 'Show', exact: true }), 'all');
  await expect(page).toHaveURL(/view=list/);
  await expect(page.getByRole('button', { name: 'List view' })).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(page.getByRole('button', { name: 'List view' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('combobox', { name: 'Show', exact: true })).toHaveText('All material');
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeVisible();
});

test('material management keeps all source and maintenance actions', async ({ page }) => {
  await pageWorkspace(page);
  await page.goto('/library/material-1');
  for (const action of ['Save material details', 'Archive material', 'Reindex material', 'Delete material', 'Resolve concept tags', 'Open source version']) await expect(page.getByRole('button', { name: action, exact: true })).toBeVisible();
  for (const action of ['Back to Library', 'Study in chat', 'Quiz this material']) await expect(page.getByRole('link', { name: action, exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Delete material', exact: true }).click();
  const confirm = page.getByRole('dialog', { name: 'Delete material confirmation' });
  await expect(confirm.getByRole('button', { name: 'Confirm deletion' })).toBeVisible();
  await confirm.getByRole('button', { name: 'Keep material' }).click();
});

test('assessment creation retains all twelve question formats and optional source settings', async ({ page }) => {
  await pageWorkspace(page);
  await page.goto('/assessments');
  await page.getByRole('button', { name: 'Create assessment', exact: true }).click();
  await expect(page.getByRole('tab', { name: 'Create new', exact: true })).toHaveAttribute('aria-selected', 'true');
  await page.getByText('Practice settings · optional', { exact: true }).click();
  for (const name of ['Multiple choice', 'Multiple select', 'True / false', 'Short answers', 'Written responses', 'Numerical', 'Fill in the blanks', 'Matching', 'Ordering', 'Essays', 'Proofs', 'Case studies']) await expect(page.getByRole('checkbox', { name, exact: true })).toBeVisible();
  await expect(page.getByText('Study materials', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Assessment instructions' })).toBeVisible();
  await expect(page.getByRole('spinbutton', { name: 'Number of questions' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Generate assessment' })).toBeVisible();
});

test('Settings shortcuts retain every profile, preference, password, memory and notification control', async ({ page }) => {
  await pageWorkspace(page);
  await page.goto('/settings');
  await expect(page.getByRole('button', { name: 'Edit profile', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Password', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Change password', exact: true })).toBeInViewport();
  await page.getByRole('link', { name: 'Preferences', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Chat font size' })).toBeInViewport();
  await expect(page.getByRole('switch', { name: 'Open sources in Mentra' })).toBeVisible();
  await expect(page.getByRole('switch', { name: 'Save chat assessments automatically' })).toBeVisible();
  await page.getByRole('tab', { name: 'Memories', exact: true }).click();
  await expect(page.getByRole('switch', { name: 'Let Mentra save useful memories' })).toBeVisible();
  await page.getByRole('tab', { name: 'Notifications', exact: true }).click();
  for (const name of ['Enable notifications', 'Event reminders']) await expect(page.getByRole('switch', { name, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save settings' })).toBeVisible();
});

test('notification actions remain available in the new feed layout', async ({ page }) => {
  await pageWorkspace(page);
  await page.goto('/notifications');
  for (const action of ['Mark read', 'Dismiss', 'Refresh']) await expect(page.getByRole('button', { name: action, exact: true })).toBeVisible();
  for (const action of ['Preferences', 'View event']) await expect(page.getByRole('link', { name: action, exact: true })).toBeVisible();
  await expect(page.getByRole('switch', { name: 'Unread only' })).toBeVisible();
});

test('onboarding keeps profile, calibration, skip, sign-out and theme choices', async ({ page }, info) => {
  await pageWorkspace(page);
  const estimates = Object.fromEntries(['overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity'].map(key => [key, { value: null, confidence: 0, evidence_count: 0 }]));
  let details: Record<string, string> | null = null;
  await page.route('**/api/v1/student-profile', route => route.fulfill({ json: { learner_id: 'polish-user', details, estimates, onboarding_phase: details ? 'calibration' : 'information', calibration_status: 'not_started', evaluation_status: 'not_started', version: 1, context_version: 1 } }));
  await page.route('**/api/v1/student-profile/calibration', route => route.fulfill({ json: null }));
  await page.goto('/onboarding');
  await expect(page.getByRole('heading', { name: 'Make Mentra yours' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Education level' })).toBeVisible();
  await page.screenshot({ path: info.outputPath('onboarding-profile.png') });
  details = { education_level: 'college', field_of_study: 'Physics', learning_goal: 'Understand motion', learning_preference: 'balanced', explanation_depth: 'standard' };
  await page.reload();
  for (const action of ['Start quick calibration', 'Skip for now', 'Sign out']) await expect(page.getByRole('button', { name: action, exact: true })).toBeVisible();
  for (const name of ['Light theme', 'Dark theme', 'System theme']) await expect(page.getByRole('radio', { name, exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath('onboarding-calibration.png') });
});
