import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { richChat } from './renovation-rich-fixtures';
import { chooseOption } from './select-helpers';

function chart() {
  return { type: 'LineChart', title: 'Response model', enableControls: true, xKey: 'x', series: [{ dataKey: 'y', name: 'Response' }, { dataKey: 'z', name: 'Follow-on' }], data: [{ x: 1, y: 2, z: 3 }, { x: 2, y: 8, z: 9 }],
    model: { kind: 'illustrative', note: 'A hypothetical response curve, not measurements.', parameters: [{ key: 'gain', label: 'Gain', value: 2, min: 0, max: 10, step: .1 }], equations: [{ dataKey: 'z', expression: 'y + 1' }, { dataKey: 'y', expression: 'gain*x^2' }] } };
}
for (const width of [390, 1280]) test(`equation controls recompute dependencies, reset and fullscreen at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  const state = await richChat(page, '```recharts\n' + JSON.stringify(chart()) + '\n```');
  await page.goto('/chat/polish-chat'); await expect(page.locator('.recharts-wrapper')).toBeVisible();
  await expect(page.getByText('Illustrative equation model', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'View data', exact: true }).click();
  const cells = page.locator('.recharts-figure tbody tr');
  await expect(cells.nth(1).locator('td').first()).toHaveText('8');
  const slider = page.getByRole('slider', { name: 'Adjust selected value' });
  await slider.focus(); await page.keyboard.press('ArrowRight');
  await expect(cells.nth(1).locator('td').first()).toHaveText('8.4');
  await page.getByRole('button', { name: 'Number', exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Selected value', exact: true }).fill('3');
  await expect(cells.nth(0).locator('td').first()).toHaveText('3');
  await expect(cells.nth(1).locator('td').first()).toHaveText('12');
  await expect(cells.nth(1).locator('td').nth(1)).toHaveText('13');
  await page.getByRole('button', { name: 'Slider', exact: true }).click();
  await expect(slider).toHaveValue('3');
  await page.getByRole('button', { name: 'Number', exact: true }).click();
  await expect(page.getByRole('spinbutton', { name: 'Selected value', exact: true })).toHaveValue('3');
  await chooseOption(page.getByRole('combobox', { name: 'Chart value', exact: true }), 'x');
  await page.getByRole('spinbutton', { name: 'Selected value', exact: true }).fill('4');
  await expect(cells.nth(0).locator('td').first()).toHaveText('48');
  await expect(cells.nth(1).locator('td').first()).toHaveText('12');
  await page.getByRole('combobox', { name: 'Chart value', exact: true }).click();
  await expect(page.getByRole('listbox').locator('[data-value="y"], [data-value="z"]')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(cells.nth(0).locator('td').first()).toHaveText('2');
  await page.getByRole('button', { name: 'Expand', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Expanded chart: Response model' });
  await dialog.getByRole('spinbutton', { name: 'Selected value', exact: true }).fill('4');
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(cells.nth(1).locator('td').first()).toHaveText('16');
  expect(state.submissions).toHaveLength(0);
});

test('invalid equation domains preserve valid graph and Reset restores it', async ({ page }) => {
  const spec = chart(); spec.model.equations = [{ dataKey: 'y', expression: 'sqrt(gain-x)' }];
  await richChat(page, '```recharts\n' + JSON.stringify(spec) + '\n```'); await page.goto('/chat/polish-chat');
  await page.getByRole('button', { name: 'View data', exact: true }).click();
  await page.getByRole('button', { name: 'Number', exact: true }).click();
  const input = page.getByRole('spinbutton', { name: 'Selected value', exact: true });
  const cell = page.locator('.recharts-figure tbody tr').first().locator('td').first();
  await expect(cell).toHaveText('1'); await input.fill('0');
  await expect(input).toHaveAttribute('aria-invalid', 'true'); await expect(cell).toHaveText('1');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(input).toHaveValue('2'); await expect(input).toHaveAttribute('aria-invalid', 'false');
});

test('exports include current model equations, assumptions and parameter values', async ({ page }) => {
  await richChat(page, '```recharts\n' + JSON.stringify(chart()) + '\n```'); await page.goto('/chat/polish-chat');
  await page.getByRole('button', { name: 'Number', exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Selected value', exact: true }).fill('3');
  const pending = page.waitForEvent('download'); await page.getByRole('button', { name: 'Download SVG', exact: true }).click();
  const download = await pending; const path = await download.path(); expect(path).toBeTruthy();
  const svg = await readFile(path!, 'utf8');
  expect(svg).toContain('Illustrative model'); expect(svg).toContain('Gain = 3'); expect(svg).toContain('gain*x^2');
  expect(svg).not.toMatch(/<foreignObject|<script|var\(--/);
});

test('unsafe models fail locally and read-only models have no editing controls', async ({ page }) => {
  const bad = chart(); bad.model.equations = [{ dataKey: 'y', expression: 'window.alert(1)' }];
  const fixed = { ...chart(), enableControls: false };
  await richChat(page, '```recharts\n' + JSON.stringify(bad) + '\n```\n\n```recharts\n' + JSON.stringify(fixed) + '\n```');
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('status').filter({ hasText: 'unsupported or invalid data' })).toBeVisible();
  await expect(page.locator('.recharts-wrapper')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Chart controls' })).toHaveCount(0);
});

test('per-row inputs drive outputs without becoming chart series', async ({ page }) => {
  const spec = { type: 'BarChart', title: 'Hypothetical revenue', enableControls: true, xKey: 'product', series: [{ dataKey: 'revenue', name: 'Revenue' }], data: [{ product: 'A', quantity: 2, revenue: null }, { product: 'B', quantity: 4, revenue: null }],
    model: { kind: 'illustrative', note: 'Constant hypothetical price, excluding costs.', parameters: [{ key: 'price', label: 'Price', value: 3, min: 1, max: 10 }], inputs: [{ dataKey: 'quantity', label: 'Quantity', min: 0, max: 100, unit: 'units' }], equations: [{ dataKey: 'revenue', expression: 'price*quantity' }] } };
  await richChat(page, '```recharts\n' + JSON.stringify(spec) + '\n```'); await page.goto('/chat/polish-chat');
  await page.getByRole('button', { name: 'View data', exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Quantity (units)', exact: true })).toBeVisible();
  await chooseOption(page.getByRole('combobox', { name: 'Chart value', exact: true }), 'quantity');
  await page.getByRole('button', { name: 'Number', exact: true }).click();
  const value = page.getByRole('spinbutton', { name: 'Selected value', exact: true });
  await value.fill('5');
  const rows = page.locator('.recharts-figure tbody tr');
  await expect(rows.first().locator('td').nth(1)).toHaveText('15');
  await expect(rows.nth(1).locator('td').nth(1)).toHaveText('12');
  await value.fill('-1'); await expect(value).toHaveAttribute('aria-invalid', 'true');
  await expect(rows.first().locator('td').nth(1)).toHaveText('15');
  await page.getByRole('button', { name: 'Slider', exact: true }).click();
  await expect(page.getByRole('slider', { name: 'Adjust selected value' })).toHaveValue('5');
});

for (const type of ['LineChart', 'BarChart', 'AreaChart', 'ComposedChart', 'PieChart', 'RadarChart', 'ScatterChart']) test(`${type} calculates model outputs before rendering`, async ({ page }) => {
  const spec = { type, title: 'Computed values', xKey: 'category', enableControls: true,
    data: [1,2,3].map((quantity, index) => ({ category: type === 'ScatterChart' ? quantity : String.fromCharCode(65 + index), quantity, y: null })),
    series: [{ dataKey: 'y', name: 'Output', ...(type === 'ComposedChart' ? { type: 'Bar' } : {}) }],
    model: { kind: 'illustrative', note: 'Hypothetical scaled quantities.', parameters: [{ key: 'gain', label: 'Gain', value: 2, min: 1, max: 5 }], inputs: [{ dataKey: 'quantity', label: 'Quantity', min: 0, max: 10 }], equations: [{ dataKey: 'y', expression: 'gain*quantity' }] } };
  await richChat(page, '```recharts\n' + JSON.stringify(spec) + '\n```'); await page.goto('/chat/polish-chat');
  await expect(page.locator('.recharts-wrapper')).toBeVisible();
  await page.getByRole('button', { name: 'View data', exact: true }).click();
  await page.getByRole('button', { name: 'Number', exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Selected value', exact: true }).fill('3');
  const rows = page.locator('.recharts-figure tbody tr');
  await expect(rows.first().locator('td').nth(1)).toHaveText('3');
  await expect(rows.nth(2).locator('td').nth(1)).toHaveText('9');
});
