import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { writeFile } from 'node:fs/promises';

test('production entry routes and 200-message typing expose measured browser costs', async ({ page }, info) => {
  await workspace(page, false, true, '', false, 200);
  await page.addInitScript(() => {
    const state = { layoutShift: 0 };
    (window as unknown as { renovationLayout: typeof state }).renovationLayout = state;
    new PerformanceObserver(list => { for (const entry of list.getEntries()) {
      const shift = entry as PerformanceEntry & { value: number; hadRecentInput: boolean };
      if (!shift.hadRecentInput) state.layoutShift += shift.value;
    } }).observe({ type: 'layout-shift', buffered: true });
  });
  const results: unknown[] = [];
  for (const route of ['/library', '/assessments', '/chat/polish-chat']) {
    await page.goto(route);
    if (route.startsWith('/chat')) await expect(page.getByLabel('Ask Mentra anything')).toBeEnabled();
    else await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const result = await page.evaluate(route => ({ route, javascript: performance.getEntriesByType('resource').filter(entry => /\.js(?:\?|$)/.test(entry.name)).map(entry => { const resource = entry as PerformanceResourceTiming; return { name: new URL(resource.name).pathname, bytes: resource.decodedBodySize }; }), readyMs: performance.now(), layoutShift: (window as unknown as { renovationLayout: { layoutShift: number } }).renovationLayout.layoutShift }), route);
    expect(result.layoutShift).toBeLessThanOrEqual(.1);
    results.push(result);
  }
  await page.evaluate(() => {
    const state = { samples: [] as number[], longTasks: [] as number[] };
    (window as unknown as { renovationProfile: typeof state }).renovationProfile = state;
    new PerformanceObserver(list => { state.longTasks.push(...list.getEntries().map(entry => entry.duration)); }).observe({ type: 'longtask' });
    document.addEventListener('input', () => { const started = performance.now(); requestAnimationFrame(() => state.samples.push(performance.now() - started)); });
  });
  await page.getByLabel('Ask Mentra anything').pressSequentially('Explain momentum clearly', { delay: 20 });
  await expect(page.getByLabel('Ask Mentra anything')).toHaveValue('Explain momentum clearly');
  const typing = await page.evaluate(() => (window as unknown as { renovationProfile: { samples: number[]; longTasks: number[] } }).renovationProfile);
  expect(typing.samples.length).toBeGreaterThan(0);
  const artifact = info.outputPath('browser-performance.json');
  await writeFile(artifact, JSON.stringify({ results, typing }, null, 2));
  await info.attach('browser-performance.json', { path: artifact, contentType: 'application/json' });
});
