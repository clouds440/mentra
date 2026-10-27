import { expect, test } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { workspace } from './renovation-fixtures';

test('completed rich messages do not rerender while typing or receiving unchanged history', async ({ page }, info) => {
  await page.addInitScript(() => {
    type Fiber = { flags: number; child: Fiber | null; sibling: Fiber | null; elementType?: { displayName?: string }; type?: { displayName?: string; name?: string } };
    const watched = new Set(['ChatMessage', 'MarkdownContent', 'ChoiceCard', 'InlineIcon']);
    let previous = new Set<Fiber>();
    const counts: Record<string, number> = {};
    const state = { counts, samples: [] as number[], longTasks: [] as number[] };
    Object.assign(window, { richRenderProfile: state, __REACT_DEVTOOLS_GLOBAL_HOOK__: {
      supportsFiber: true, renderers: new Map(), inject: () => 1,
      onCommitFiberRoot: (_renderer: number, root: { current: Fiber }) => {
        const next = new Set<Fiber>();
        function visit(fiber: Fiber | null) {
          while (fiber) {
            next.add(fiber);
            const name = fiber.elementType?.displayName ?? fiber.type?.displayName ?? fiber.type?.name ?? '';
            if (!previous.has(fiber) && (fiber.flags & 1) && watched.has(name)) counts[name] = (counts[name] ?? 0) + 1;
            visit(fiber.child); fiber = fiber.sibling;
          }
        }
        visit(root.current); previous = next;
      }, onCommitFiberUnmount: () => {},
    } });
    new PerformanceObserver(list => state.longTasks.push(...list.getEntries().map(entry => entry.duration))).observe({ type: 'longtask' });
    document.addEventListener('input', () => { const start = performance.now(); requestAnimationFrame(() => state.samples.push(performance.now() - start)); });
  });
  await workspace(page);
  const conversation = { id: 'polish-chat', title: 'Performance', revision: 2, message_count: 200, selection: { mode: 'STANDARD', context_ids: [], document_ids: [] }, created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00Z' };
  const items = Array.from({ length: 200 }, (_, i) => ({ id: `perf-${i}`, conversation_id: conversation.id, sequence: i + 1, role: i % 2 ? 'assistant' : 'user', content: i % 2 ? ':icon[BookOpen] A clear explanation with :color[meaningful emphasis]{tone="success"}.' : 'Explain the concept clearly.', created_at: conversation.created_at,
    ...(i % 2 ? { interactions: [{ id: `bars-${i}`, kind: 'value_bars', question: 'Relative difficulty', bars: [{ label: 'Concept A', value: 3, max: 5 }, { label: 'Concept B', value: 4, max: 5 }] }] } : {}) }));
  let reads = 0;
  await page.route('**/api/v1/conversations/polish-chat/status*', route => { reads++; return route.fulfill({ json: { conversation, items, turn: null, has_more: false, next_cursor: null } }); });
  await page.route('**/api/v1/conversations/sync*', route => route.fulfill({ json: { conversations: [conversation], reset: false, cursor: conversation.revision, has_more: false, deleted_ids: [], list_cursor: null } }));
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('meter')).toHaveCount(200);
  await expect(page.locator('.rich-icon svg')).toHaveCount(100);
  expect(await page.evaluate(() => performance.getEntriesByType('resource').filter(entry => /lucideIconCatalog/.test(entry.name)).length)).toBe(1);
  expect(await page.evaluate(() => performance.getEntriesByType('resource').filter(entry => /MermaidDiagram|mermaid\.core|flowDiagram/.test(entry.name)).length)).toBe(0);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const initial = await page.evaluate(() => (window as any).richRenderProfile.counts);
  expect(initial.ChatMessage).toBeGreaterThan(0); expect(initial.MarkdownContent).toBeGreaterThan(0); expect(initial.ChoiceCard).toBeGreaterThan(0);
  await page.evaluate(() => { const state = (window as any).richRenderProfile; for (const key of Object.keys(state.counts)) state.counts[key] = 0; state.samples = []; state.longTasks = []; });
  await page.getByLabel('Ask Mentra anything').pressSequentially('Explain momentum clearly', { delay: 20 });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const typingTasks = await page.evaluate(() => [...(window as any).richRenderProfile.longTasks]) as number[];
  const before = reads; conversation.revision++;
  await page.evaluate(() => { const channel = new BroadcastChannel('mentra-chat-polish-user'); channel.postMessage('changed'); channel.close(); });
  await expect.poll(() => reads).toBeGreaterThan(before);
  await page.evaluate(() => { localStorage.setItem('mentra-chat-font-size', 'large'); window.dispatchEvent(new StorageEvent('storage', { key: 'mentra-chat-font-size', newValue: 'large' })); });
  await expect(page.getByRole('article', { name: 'Mentra response' }).last().locator('.chat-prose')).toHaveCSS('font-size', '18px');
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const result = await page.evaluate(() => (window as any).richRenderProfile) as { counts: Record<string, number>; samples: number[]; longTasks: number[] };
  expect(result.counts).toEqual({ ChatMessage: 0, MarkdownContent: 0, ChoiceCard: 0, InlineIcon: 0 });
  expect(result.samples.length).toBeGreaterThan(10);
  const sorted = [...result.samples].sort((a, b) => a - b); const p95 = sorted[Math.floor(sorted.length * .95)];
  expect(p95).toBeLessThan(50);
  const artifact = info.outputPath('rich-render-performance.json');
  await writeFile(artifact, JSON.stringify({ ...result, typingLongTasks: typingTasks, typingP95Ms: p95, messages: 200, staticBars: 200 }, null, 2));
  await info.attach('rich-render-performance', { path: artifact, contentType: 'application/json' });
  items[199].interactions![0].bars[0].value = 2; conversation.revision++;
  await page.evaluate(() => { const channel = new BroadcastChannel('mentra-chat-polish-user'); channel.postMessage('changed'); channel.close(); });
  await expect(page.getByRole('meter', { name: 'Concept A' }).last()).toHaveAttribute('aria-valuenow', '2');
});
