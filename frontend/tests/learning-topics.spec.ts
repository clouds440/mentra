import { test, expect, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';

const topic = { id: '00000000-0000-4000-8000-000000000091', name: 'Differentiation rules', scope: 'Rules for differentiating functions, including compositions and products.', context_id: 'context-1', subskill_count: 12, checked_count: 2, revision: 1 };
const skills = Array.from({ length: 12 }, (_, index) => ({ concept_id: `skill-${index}`, name: index === 11 ? 'Chain rule' : `Differentiation skill ${index + 1}`, context_id: 'context-1', topic_id: topic.id, topic_name: topic.name, ability: index === 11 ? 'Differentiate composite functions.' : 'Apply this differentiation rule.', mastery: null, estimate_confidence: null, retention_confidence: null, knowledge_status: 'insufficient_evidence', misconceptions: [] }));

async function setup(page: Page) {
  await workspace(page, false, true);
  await page.route('**/api/v1/learning/topics**', async route => {
    const url = new URL(route.request().url());
    const query = url.searchParams.get('query') ?? '';
    const offset = Number(url.searchParams.get('offset') ?? 0);
    if (url.pathname.endsWith('/subskills')) {
      const matching = skills.filter(skill => skill.name.toLowerCase().includes(query.toLowerCase()));
      return route.fulfill({ json: { topic, items: matching.slice(offset, offset + 10), total: matching.length, limit: 10, offset, generated_at: '2026-10-27T00:00:00Z' } });
    }
    return route.fulfill({ json: { items: [{ ...topic, matching_skills: query ? ['Chain rule'] : [] }], total: 1, ungrouped_count: 0, limit: 10, offset: 0, generated_at: '2026-10-27T00:00:00Z' } });
  });
}

test('progress groups skills and finds a late-page subskill by its parent', async ({ page }) => {
  await setup(page);
  await page.goto('/progress');
  await expect(page.getByRole('button', { name: 'Explore Differentiation rules' })).toBeVisible();
  await expect(page.getByText('2 of 12 tracked subskills checked')).toBeVisible();
  await expect(page.getByText('Differentiation skill 1', { exact: true })).toHaveCount(0);
  await page.getByRole('searchbox', { name: 'Search topics and subskills' }).fill('chain');
  await expect(page.getByText('Matches: Chain rule')).toBeVisible();
  await page.getByRole('button', { name: 'Explore Differentiation rules' }).click();
  const dialog = page.getByRole('dialog', { name: 'Topic subskills' });
  await expect(dialog.getByText('Chain rule', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Differentiate composite functions.', {exact:true})).toBeVisible();
  await expect(dialog.getByRole('link', { name: 'Practise this skill' })).toHaveAttribute('href', /concept=skill-11/);
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Explore Differentiation rules' })).toBeFocused();
});

test('mobile selection preserves subskills across pages and requires enough questions', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await setup(page);
  await page.goto(`/assessments?tab=create&context=context-1&learning_topic=${topic.id}&topic=Differentiation`);
  await expect(page.getByRole('checkbox', { name: 'Differentiation skill 1', exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: 'Differentiation skill 1', exact: true }).check();
  await page.getByRole('navigation', { name: 'Practice targets' }).getByRole('button', { name: 'Next page' }).click();
  await page.getByRole('checkbox', { name: 'Chain rule', exact: true }).check();
  await expect(page.getByText('2 selected subskills. Choose at least that many questions.')).toBeVisible();
  await page.getByRole('spinbutton', { name: 'Number of questions' }).fill('1');
  await expect(page.getByRole('button', { name: 'Generate assessment' })).toBeDisabled();
  await page.getByRole('spinbutton', { name: 'Number of questions' }).fill('3');
  await page.getByRole('navigation', { name: 'Practice targets' }).getByRole('button', { name: 'Previous page' }).click();
  await expect(page.getByRole('checkbox', { name: 'Differentiation skill 1', exact: true })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Generate assessment' })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test('a broad topic link starts with sample coverage rather than selecting every child', async ({ page }) => {
  await setup(page);
  await page.goto(`/assessments?tab=create&context=context-1&learning_topic=${topic.id}&topic=Differentiation`);
  await expect(page.getByText('Leave subskills unselected for a useful sample.', { exact: false })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: 'Differentiation skill 1', exact: true })).not.toBeChecked();
  let payload: Record<string, unknown> | undefined;
  await page.route('**/api/v1/assessments/generation-jobs', async route => {
    payload = route.request().postDataJSON();
    await route.fulfill({ json: { id: 'topic-generation', state: 'queued', title: 'Differentiation', completed_parts: 0, total_parts: 3, result: null, error: null, can_retry: false } });
  });
  await page.getByRole('button', { name: 'Generate assessment' }).click();
  await expect.poll(() => payload?.topic_id).toBe(topic.id);
  expect(payload?.concept_ids).toEqual([]);
});

test('saved topic and selected subskills survive a tab reload', async ({ page }) => {
  await setup(page);
  await page.goto('/assessments?tab=create');
  await page.getByText('Choose a saved topic · optional', { exact:true }).click();
  await page.getByRole('button', { name:'Differentiation rules 12 subskills', exact:true }).click();
  const skill = page.getByRole('checkbox', { name:'Differentiation skill 1', exact:true });
  await skill.check();
  await page.reload();
  await expect(page.getByRole('checkbox', { name:'Differentiation skill 1', exact:true })).toBeChecked();
  await expect(page.getByText('1 selected subskills. Choose at least that many questions.')).toBeVisible();
});
