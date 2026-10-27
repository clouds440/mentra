import { expect, test } from '@playwright/test';
import { richChat, trackRichRenders } from './renovation-rich-fixtures';

const base = { type: 'BarChart', title: 'Study time', description: 'Provided values, in minutes.', xKey: 'topic', unit: 'minutes', data: [{ topic: 'Algebra', minutes: 20 }, { topic: 'Geometry', minutes: 30 }, { topic: 'Statistics', minutes: 25 }], series: [{ dataKey: 'minutes', name: 'Study time' }] };
const fence = (spec: unknown) => '```recharts\n' + JSON.stringify(spec) + '\n```';
const familyAssets = /\/(?:RechartsFigure|LineView|BarView|AreaView|ComposedView|PieView|RadarView|ScatterView)-/;

for (const type of ['LineChart', 'BarChart', 'AreaChart', 'ComposedChart', 'PieChart', 'RadarChart', 'ScatterChart']) test(`${type} has visible data and fullscreen controls`, async ({ page }, info) => {
  if (type === 'BarChart') { await page.setViewportSize({ width: 390, height: 844 }); await page.emulateMedia({ colorScheme: 'dark' }); }
  const spec = { ...base, type, ...(type === 'ComposedChart' ? { series: [{ ...base.series[0], type: 'Bar' }] } : {}), ...(type === 'ScatterChart' ? { data: base.data.map((row, i) => ({ ...row, topic: i + 1 })) } : {}) };
  await richChat(page, `Here are the supplied values.\n\n${fence(spec)}`);
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/chat/polish-chat');
  const chart = page.locator('.recharts-figure');
  await expect(chart.locator('.recharts-wrapper')).toBeVisible();
  await expect(chart.locator('svg').first()).toBeVisible();
  await chart.getByRole('button', { name: 'View data', exact: true }).click();
  await expect(chart.getByRole('table')).toContainText('20');
  await expect(chart.getByRole('table')).toContainText('30');
  await chart.getByRole('button', { name: 'Expand', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Expanded chart: Study time' });
  await expect(viewer.locator('.recharts-wrapper')).toBeVisible();
  expect(await viewer.boundingBox()).toMatchObject({ x: 0, y: 0, ...page.viewportSize()! });
  await expect(viewer.getByRole('button', { name: 'Close', exact: true })).toBeInViewport();
  if (type === 'BarChart') {
    const ticks = viewer.locator('.recharts-yAxis-tick-labels .recharts-cartesian-axis-tick-value');
    await expect.poll(() => ticks.count()).toBeGreaterThan(1);
    const expectedHeight = await ticks.evaluateAll(nodes => {
      const ticks = nodes.map(node => ({ value: Number(node.textContent), y: node.getBoundingClientRect().y })).sort((a, b) => a.value - b.value);
      return (ticks[0].y - ticks.at(-1)!.y) * 20 / (ticks.at(-1)!.value - ticks[0].value);
    });
    await expect.poll(() => viewer.locator('.recharts-bar-rectangle path').first().evaluate((node, expected) => Math.abs(node.getBoundingClientRect().height - expected), expectedHeight)).toBeLessThan(2);
    await page.screenshot({ path: info.outputPath('chart-mobile-fullscreen.png'), animations: 'disabled' });
  }
  await page.keyboard.press('Escape');
  await expect(viewer).toHaveCount(0);
  await expect(chart.getByRole('button', { name: 'Expand', exact: true })).toBeFocused();
  await chart.getByRole('button', { name: 'View source', exact: true }).click();
  await expect(chart.locator('code')).toContainText(JSON.stringify(spec));
  expect(errors).toEqual([]);
});

test('chart modules stay unloaded for text and offscreen charts; repeated charts reuse a family', async ({ page }) => {
  const requests: string[] = []; page.on('request', request => { if (familyAssets.test(request.url())) requests.push(request.url()); });
  await richChat(page, 'Ordinary text without a chart.'); await page.goto('/chat/polish-chat');
  await expect(page.getByText('Ordinary text without a chart.', { exact: true })).toBeVisible();
  expect(requests).toEqual([]);
  await richChat(page, fence(base) + '\n\n' + Array.from({ length: 80 }, (_, i) => `Paragraph ${i}: The explanation stays readable without waiting for charts.`).join('\n\n'));
  await page.goto('/chat/polish-chat');
  await expect(page.getByText('Chart', { exact: true })).toBeAttached();
  await expect(page.getByText('Paragraph 79:', { exact: false })).toBeVisible();
  expect(requests).toEqual([]);
  await page.getByText('Chart', { exact: true }).scrollIntoViewIfNeeded();
  await expect(page.locator('.recharts-figure .recharts-wrapper')).toBeVisible();
  expect(requests.filter(url => /\/BarView-/.test(url))).toHaveLength(1);
  expect(requests.filter(url => /\/(?:PieView|RadarView|ScatterView)-/.test(url))).toHaveLength(0);
  await richChat(page, [fence(base), fence(base)].join('\n\n')); await page.goto('/chat/polish-chat');
  await expect(page.locator('.recharts-figure')).toHaveCount(2);
  expect(requests.filter(url => /\/BarView-/.test(url))).toHaveLength(2); // one per document load, shared within that document
});

for (const chunk of ['RechartsFigure', 'BarView']) test(`failed ${chunk} preserves surrounding text and source`, async ({ page }) => {
  await richChat(page, 'Before.\n\n' + fence(base) + '\n\nAfter.');
  await page.route(`**/${chunk}-*.js`, route => route.abort());
  await page.goto('/chat/polish-chat');
  await expect(page.getByText('Before.', { exact: true })).toBeVisible();
  await expect(page.getByText('After.', { exact: true })).toBeVisible();
  await expect(page.getByText(chunk === 'BarView' ? 'This chart could not be displayed. Its data and source are still available.' : 'This chart could not be loaded. Its source is available below.')).toBeVisible();
  if (chunk === 'BarView') await page.getByRole('button', { name: 'View source', exact: true }).click();
  await expect(page.locator('code')).toContainText('Algebra');
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Continue without the chart');
});

const invalid: Record<string, unknown> = {
  'JSX': '<BarChart data={window.alert(1)} />',
  'extra props': { ...base, onClick: 'alert(1)' },
  'prototype key': { ...base, xKey: 'constructor' },
  'numeric strings': { ...base, data: [{ topic: 'Algebra', minutes: '20' }] },
  'too many rows': { ...base, data: Array.from({ length: 201 }, () => base.data[0]) },
  'negative pie': { ...base, type: 'PieChart', data: [{ topic: 'Algebra', minutes: -1 }] },
  'empty pie': { ...base, type: 'PieChart', data: [{ topic: 'Algebra', minutes: 0 }] },
  'missing values': { ...base, data: [{ topic: 'Algebra' }] },
  'callbacks in series': { ...base, series: [{ ...base.series[0], shape: '<script />' }] },
  'duplicate series': { ...base, series: [base.series[0], base.series[0]] },
  'nonfinite values': { ...base, data: [{ topic: 'Algebra', minutes: 1e15 }] },
  'all missing series': { ...base, data: [{ topic: 'Algebra', minutes: null }] },
  'underspecified radar': { ...base, type: 'RadarChart', data: [base.data[0]] },
};
for (const [name, spec] of Object.entries(invalid)) test(`invalid ${name} stays local without loading a chart family`, async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => { if (/\/(?:BarView|PieView)-/.test(request.url())) requests.push(request.url()); });
  await richChat(page, fence(spec)); await page.goto('/chat/polish-chat');
  await expect(page.getByText('This chart has unsupported or invalid data. Its source is available below.')).toBeVisible();
  await expect(page.locator('code')).toBeVisible();
  expect(requests).toEqual([]);
});

test('at most three charts render and reduced motion keeps exact tooltip data', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await richChat(page, Array.from({ length: 4 }, () => fence(base)).join('\n\n'));
  await page.goto('/chat/polish-chat');
  const wrappers = page.locator('.recharts-figure');
  await expect(page.locator('[data-visual-kind="chart"]')).toHaveCount(3);
  for (const block of await page.locator('[data-visual-kind="chart"]').all()) { await block.scrollIntoViewIfNeeded(); await expect(block.locator('.recharts-wrapper')).toBeAttached(); }
  await expect(wrappers).toHaveCount(3);
  const chart = wrappers.last();
  await chart.scrollIntoViewIfNeeded();
  await expect(chart.locator('.recharts-bar-rectangle').first()).toBeVisible();
  await chart.getByRole('application', { name: 'Study time', exact: true }).focus();
  await expect(chart.locator('.recharts-tooltip-wrapper')).toBeVisible();
  await expect(chart.locator('.recharts-tooltip-wrapper')).toContainText('20');
  await page.keyboard.press('ArrowRight');
  await expect(chart.locator('.recharts-tooltip-wrapper')).toContainText('Geometry');
  await expect(chart.locator('.recharts-tooltip-wrapper')).toContainText('30');
  await expect(chart.locator('.recharts-tooltip-wrapper')).toContainText('30 minutes');
  await expect(page.locator('.code-block')).toHaveCount(1);
});

test('numeric field names cannot become SVG properties and text stays escaped', async ({ page }) => {
  const external: string[] = []; const errors: string[] = [];
  page.on('request', request => { if (request.url().includes('chart-external.invalid')) external.push(request.url()); });
  page.on('pageerror', error => errors.push(error.message));
  const spec = { type: 'PieChart', title: 'Field safety', xKey: 'fill', series: [{ dataKey: 'onClick', name: 'Count' }], data: [{ fill: '<img src="https://chart-external.invalid/image">', onClick: 20 }, { fill: 'Other', onClick: 30 }] };
  await richChat(page, fence(spec)); await page.goto('/chat/polish-chat');
  const chart = page.locator('.recharts-figure');
  await expect(chart.locator('.recharts-pie-sector')).toHaveCount(2);
  await expect(chart.locator('img')).toHaveCount(0);
  await chart.getByRole('button', { name: 'View data', exact: true }).click();
  await expect(chart.getByRole('table')).toContainText(spec.data[0].fill);
  await expect(chart.getByRole('table')).toContainText('20');
  expect(external).toEqual([]); expect(errors).toEqual([]);
});

test('multiple composed series preserve gaps, negative values and single-point areas', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const composed = { ...base, type: 'ComposedChart', data: [{ topic: 'A', observed: -2, trend: 1, range: 2 }, { topic: 'B', observed: 0, trend: null, range: 3 }, { topic: 'C', observed: 4, trend: 3, range: 5 }], series: [{ dataKey: 'observed', type: 'Bar' }, { dataKey: 'trend', type: 'Line' }, { dataKey: 'range', type: 'Area' }] };
  await richChat(page, fence(composed) + '\n\n' + fence({ ...base, type: 'AreaChart', data: [base.data[0]] }));
  await page.goto('/chat/polish-chat');
  for (const block of await page.locator('[data-visual-kind="chart"]').all()) { await block.scrollIntoViewIfNeeded(); await expect(block.locator('.recharts-wrapper')).toBeAttached(); }
  const chart = page.locator('.recharts-figure').first();
  // A zero-height bar has no visible rectangle; its exact zero remains in data.
  await expect(chart.locator('.recharts-bar-rectangle')).toHaveCount(2);
  await expect(chart.locator('.recharts-line-dot')).toHaveCount(2);
  await expect(chart.locator('.recharts-area-area')).toBeVisible();
  await chart.getByRole('button', { name: 'View data', exact: true }).click();
  await expect(chart.getByRole('table')).toContainText('-2');
  await expect(chart.getByRole('table')).toContainText('—');
  await expect(chart.getByRole('table')).toContainText('0');
  await expect(page.locator('.recharts-figure').last().locator('.recharts-area-dot')).toHaveCount(1);
});

test('visible charts do not rerender on typing, unchanged refresh or font changes', async ({ page }, info) => {
  await trackRichRenders(page, ['ChatMessage', 'MarkdownContent', 'RechartsFigure', 'ChartCanvas']);
  const fixture = await richChat(page, [fence(base), fence({ ...base, type: 'LineChart' }), fence({ ...base, type: 'PieChart' })].join('\n\n'));
  await page.goto('/chat/polish-chat');
  await expect(page.locator('[data-visual-kind="chart"]')).toHaveCount(3);
  for (const block of await page.locator('[data-visual-kind="chart"]').all()) { await block.scrollIntoViewIfNeeded(); await expect(block.locator('.recharts-wrapper')).toBeAttached(); }
  await expect(page.locator('.recharts-figure .recharts-wrapper')).toHaveCount(3);
  const initial = await page.evaluate(() => (window as any).richRenderProfile.counts);
  for (const name of ['ChatMessage', 'MarkdownContent', 'RechartsFigure', 'ChartCanvas']) expect(initial[name]).toBeGreaterThan(0);
  await page.evaluate(() => { const state = (window as any).richRenderProfile; for (const key of Object.keys(state.counts)) state.counts[key] = 0; state.samples = []; state.longTasks = []; });
  await page.getByLabel('Ask Mentra anything').pressSequentially('Explain the comparison clearly', { delay: 20 });
  const before = fixture.statusReads(); fixture.conversation.revision++;
  await page.evaluate(() => { const channel = new BroadcastChannel('mentra-chat-polish-user'); channel.postMessage('changed'); channel.close(); });
  await expect.poll(() => fixture.statusReads()).toBeGreaterThan(before);
  await page.evaluate(() => { localStorage.setItem('mentra-chat-font-size', 'large'); window.dispatchEvent(new StorageEvent('storage', { key: 'mentra-chat-font-size', newValue: 'large' })); });
  await expect(page.locator('.chat-prose').last()).toHaveCSS('font-size', '18px');
  const result = await page.evaluate(() => (window as any).richRenderProfile) as { counts: Record<string, number>; samples: number[]; longTasks: number[] };
  expect(result.counts).toEqual({ ChatMessage: 0, MarkdownContent: 0, RechartsFigure: 0, ChartCanvas: 0 });
  const sorted = [...result.samples].sort((a, b) => a - b); const p95 = sorted[Math.floor(sorted.length * .95)];
  expect(p95).toBeLessThan(50);
  await info.attach('chart-render-performance', { body: JSON.stringify({ ...result, typingP95Ms: p95 }), contentType: 'application/json' });
});
