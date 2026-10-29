import { expect, test, type Page } from '@playwright/test';
import { richChat, trackRichRenders } from './renovation-rich-fixtures';

async function setup(page: Page, rows = 2) {
  const spec = { type: 'BarChart', title: 'Editable values', xKey: 'label', enableControls: true,
    data: Array.from({ length: rows }, (_, index) => ({ label: `Item ${index}`, value: index ? 100 : 10 })), series: [{ dataKey: 'value' }] };
  await richChat(page, '```recharts\n' + JSON.stringify(spec) + '\n```'); await page.goto('/chat/polish-chat');
  const bars = page.locator('.recharts-bar-rectangle path');
  await expect(bars).toHaveCount(rows);
  const ticks = page.locator('.recharts-yAxis-tick-labels .recharts-cartesian-axis-tick-value');
  await expect.poll(() => ticks.count()).toBeGreaterThan(1);
  const fullHeight = await ticks.evaluateAll(nodes => {
    const values = nodes.map(node => ({ value: Number(node.textContent), y: node.getBoundingClientRect().y })).sort((a, b) => a.value - b.value);
    return (values[0].y - values.at(-1)!.y) * 100 / (values.at(-1)!.value - values[0].value);
  });
  await expect.poll(() => bars.last().evaluate(node => node.getBoundingClientRect().height)).toBeCloseTo(fullHeight, 0);
  await page.getByRole('button', { name: 'View data', exact: true }).click();
  return { bars, cell: page.locator('.recharts-figure tbody tr').first().locator('td') };
}
async function probe(page: Page) {
  return page.evaluate(() => {
    const height = () => document.querySelector('.recharts-bar-rectangle path')!.getBoundingClientRect().height;
    const state = { active: true, initial: height(), samples: [] as number[] };
    (window as any).chartMotion = state;
    const sample = () => { if (state.active) { state.samples.push(height()); requestAnimationFrame(sample); } };
    requestAnimationFrame(sample);
    return state.initial;
  });
}
async function stop(page: Page) {
  return page.evaluate(() => { const state = (window as any).chartMotion; state.active = false; return state.samples as number[]; });
}

test('numeric edits update exact values immediately and interpolate geometry', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const { bars, cell } = await setup(page);
  await page.getByRole('button', { name: 'Number', exact: true }).click();
  const initial = await probe(page);
  await page.getByRole('spinbutton', { name: 'Selected value', exact: true }).fill('80');
  await expect(cell).toHaveText('80');
  await expect.poll(() => bars.first().evaluate(node => node.getBoundingClientRect().height)).toBeCloseTo(initial * 8, 0);
  const samples = await stop(page);
  expect(samples.filter(height => height > initial + 1 && height < initial * 8 - 1).length).toBeGreaterThan(1);
});

test('continuous slider changes move while dragging and do not rerender chat content', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await trackRichRenders(page, ['ChatMessage', 'MarkdownContent', 'ChartCanvas']);
  const { bars, cell } = await setup(page);
  const initial = await probe(page);
  await page.evaluate(() => { const state = (window as any).richRenderProfile; for (const key of Object.keys(state.counts)) state.counts[key] = 0; });
  const during = await page.getByRole('slider', { name: 'Adjust selected value' }).evaluate(async input => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
    for (let index = 1; index <= 12; index++) {
      await new Promise(requestAnimationFrame);
      setter.call(input, String(10 + index * 5));
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    return [...(window as any).chartMotion.samples] as number[];
  });
  expect(during.filter(height => height > initial + 1).length).toBeGreaterThan(2);
  await expect(cell).toHaveText('70');
  await expect.poll(() => bars.first().evaluate(node => node.getBoundingClientRect().height)).toBeCloseTo(initial * 7, 0);
  const samples = await stop(page);
  const counts = await page.evaluate(() => (window as any).richRenderProfile.counts);
  expect(counts.ChatMessage).toBe(0); expect(counts.MarkdownContent).toBe(0);
  expect(counts.ChartCanvas).toBeGreaterThan(0); expect(counts.ChartCanvas).toBeLessThanOrEqual(12);
  await info.attach('live-chart-motion', { body: JSON.stringify({ initial, during, samples, counts }), contentType: 'application/json' });
});

for (const [name, rows, reducedMotion] of [['reduced motion', 2, 'reduce'], ['large charts', 121, 'no-preference']] as const) {
  test(`${name} keep direct geometry updates`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion });
    const { bars, cell } = await setup(page, rows);
    await page.getByRole('button', { name: 'Number', exact: true }).click();
    const initial = await probe(page);
    await page.getByRole('spinbutton', { name: 'Selected value', exact: true }).fill('80');
    await expect(cell).toHaveText('80');
    await expect.poll(() => bars.first().evaluate(node => node.getBoundingClientRect().height)).toBeCloseTo(initial * 8, 0);
    const samples = await stop(page);
    expect(samples.filter(height => height > initial + 1 && height < initial * 8 - 1)).toEqual([]);
  });
}
