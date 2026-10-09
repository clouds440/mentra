import { chooseOption } from './select-helpers';
import { expect, type Page } from '@playwright/test';

export async function fillProfile(page: Page, level = 'primary', field = 'General studies') {
  await expect(page.getByRole('heading', { name: 'Make Mentra yours' })).toBeVisible();
  await chooseOption(page.getByLabel('Education level', { exact: true }), level);
  await page.getByLabel('Field or area of study', { exact: true }).fill(field);
  await page.getByLabel('Primary learning goal', { exact: true }).fill('Build confidence with my studies');
  await chooseOption(page.getByLabel('Learning preference', { exact: true }), 'examples_first');
  await chooseOption(page.getByLabel('Explanation depth', { exact: true }), 'standard');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'A quick starting point' })).toBeVisible();
}

export async function finishOnboardingWithoutAssessment(page: Page) {
  await fillProfile(page);
  await page.getByRole('button', { name: 'Skip for now', exact: true }).click();
}
