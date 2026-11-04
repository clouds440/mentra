import { expect, test, type Page } from '@playwright/test';
import { richChat } from './renovation-rich-fixtures';
import { workspace } from './renovation-fixtures';

const date = '2026-11-05T00:00:00Z';
const web = (index: number) => ({ token: 'W' + index, url: 'https://example.org/article/' + index,
  title: 'Article ' + index, domain: 'example.org', favicon_url: 'https://example.org/favicon.ico',
  excerpt: 'Publisher excerpt ' + index, searched_at: date, source_date_status: 'missing' });
async function citations(page: Page) {
  const fixture = await richChat(page, 'An explanation with sources [[W1]] and [[W2]].');
  Object.assign(fixture.items[1], { web_citations: ['W1', 'W2'], web_sources: Array.from({ length: 8 }, (_, i) => web(i + 1)) });
  await page.context().route('https://example.org/**', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html>
    <meta name="color-scheme" content="light dark">
    <style>h1 { color: black; } @media (prefers-color-scheme: dark) { h1 { color: white; } }</style>
    <h1>Publisher preview</h1>` }));
  await page.route('**/api/v1/web/preview', route => {
    const { url } = route.request().postDataJSON();
    return route.fulfill({ json: url === web(2).url ? { status: 'blocked' } : { status: 'available', url } });
  });
}

test('sources open new tabs, retain previews, resize and scroll without losing chat position', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ colorScheme: null });
  await citations(page);
  await page.goto('/chat/polish-chat');
  const trigger = page.getByRole('button', { name: 'Open side panel', exact: true });
  await expect(trigger.locator('svg')).toHaveClass(/lucide-panel-right/);
  expect((await trigger.boundingBox())!.x).toBeGreaterThan((await page.getByRole('link', { name: 'Notifications' }).boundingBox())!.x);
  await trigger.click();
  await expect(page.getByRole('tabpanel', { name: 'Chat sources' })).toBeVisible();
  await page.getByRole('button', { name: 'Close tab: Chat sources' }).click();
  const open = page.getByRole('button', { name: 'Web sources (8)', exact: true });
  await expect(open).toHaveAttribute('title', 'Open in side panel');
  await open.click();
  const panel = page.getByRole('complementary', { name: 'Side panel' });
  await expect(panel).toHaveCSS('transition-property', 'width, visibility');
  const list = panel.getByRole('tabpanel', { name: 'Web sources' });
  await expect(panel.getByRole('tab', { name: 'Web sources' }).locator('svg')).toHaveClass(/lucide-list-tree/);
  const first = list.getByRole('link', { name: /Open web source W1:/ });
  await expect(first).toHaveAttribute('href', web(1).url);
  await expect(first).toHaveAttribute('target', '_blank');
  await first.click();
  const preview = panel.getByRole('tabpanel', { name: 'Article 1' });
  await expect(preview.getByRole('link', { name: 'Open in browser' })).toHaveAttribute('href', web(1).url);
  await expect(preview.locator('iframe')).toHaveAttribute('sandbox', 'allow-scripts');
  const publisher = preview.frameLocator('iframe').getByRole('heading', { name: 'Publisher preview' });
  await expect(publisher).toBeVisible();
  for (const [theme, color] of [['dark', 'rgb(255, 255, 255)'], ['light', 'rgb(0, 0, 0)']]) {
    await page.evaluate(next => window.dispatchEvent(new StorageEvent('storage', {
      key: 'mentra-theme', newValue: next, storageArea: localStorage,
    })), theme);
    await expect(publisher).toHaveCSS('color', color);
  }
  await expect(preview.getByText('Publisher excerpt 1')).toHaveCount(0);
  await preview.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(list).toBeVisible();
  await expect(panel.getByRole('tab', { name: 'Article 1' })).toBeVisible();
  await page.screenshot({ path: info.outputPath('desktop-sources.png') });
  for (let i = 2; i <= 6; i++) {
    await panel.getByRole('tab', { name: 'Web sources' }).click();
    await list.getByRole('link', { name: new RegExp('Open web source W' + i + ':') }).click();
    if (i === 2) {
      const blocked = panel.getByRole('tabpanel', { name: 'Article 2' });
      await expect(blocked.getByRole('status')).toContainText('This publisher restricts embedded previews');
      await expect(blocked.locator('iframe')).toHaveCount(0);
      await expect(blocked.getByRole('link', { name: 'Open in browser' })).toHaveAttribute('href', web(2).url);
    }
  }
  const strip = panel.getByRole('tablist');
  await expect(strip).toHaveCSS('scrollbar-width', 'none');
  const previous = panel.getByRole('button', { name: 'Scroll tabs left' });
  const next = panel.getByRole('button', { name: 'Scroll tabs right' });
  await expect(previous).toBeEnabled();
  await expect(next).toBeDisabled();
  await previous.click();
  await expect(next).toBeEnabled();
  await next.click();
  await expect(next).toBeDisabled();
  const bounds = (await strip.boundingBox())!;
  const before = await strip.evaluate(node => node.scrollLeft);
  await page.mouse.move(bounds.x + 35, bounds.y + 16);
  await page.mouse.down();
  await page.mouse.move(bounds.x + 165, bounds.y + 16, { steps: 6 });
  await page.mouse.up();
  expect(await strip.evaluate(node => node.scrollLeft)).toBeLessThan(before);
  await expect(panel.getByRole('tab', { name: 'Article 6' })).toHaveAttribute('aria-selected', 'true');
  const handle = panel.getByRole('separator', { name: 'Resize side panel' });
  const grip = (await handle.boundingBox())!;
  const width = (await panel.boundingBox())!.width;
  await page.mouse.move(grip.x + grip.width / 2, grip.y + 80);
  await page.mouse.down();
  await page.mouse.move(grip.x + grip.width / 2 - 72, grip.y + 80, { steps: 5 });
  await page.mouse.up();
  expect((await panel.boundingBox())!.width).toBeGreaterThan(width + 50);
  await expect(panel.getByRole('button', { name: 'Hide side panel', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Hide side panel', exact: true }).click();
  await expect(panel).toBeHidden();
  await page.getByRole('button', { name: 'Open side panel', exact: true }).click();
  await expect(panel.getByRole('tabpanel', { name: 'Article 6' })).toBeVisible();
  await panel.getByRole('button', { name: 'Close tab: Article 6', exact: true }).click();
  await expect(panel.getByRole('tabpanel', { name: 'Article 5' })).toBeVisible();
});

test('the mobile right drawer restores focus and supports browser links with the preference on or off', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await citations(page);
  await page.goto('/chat/polish-chat');
  const link = page.getByRole('link', { name: /Open web source W1:/ });
  const popup = page.context().waitForEvent('page');
  const nativeRequest = page.context().waitForEvent('request', { predicate: request => request.url() === web(1).url && request.isNavigationRequest() });
  await link.click({ modifiers: ['Control'] });
  const external = await popup;
  await nativeRequest;
  await external.close();
  await link.click();
  const drawer = page.getByRole('dialog', { name: 'Side panel' });
  await expect(drawer).toHaveAttribute('aria-modal', 'true');
  await expect(page.getByRole('button', { name: 'Hide side panel', exact: true })).toHaveCount(1);
  await expect.poll(async () => Math.round((await drawer.boundingBox())!.x)).toBe(31);
  await expect.poll(() => page.locator('#workspace-content').evaluate(node => (node as HTMLElement).inert)).toBe(true);
  await page.screenshot({ path: info.outputPath('mobile-sources.png') });
  await page.keyboard.press('Escape');
  await expect(drawer).toHaveCount(0);
  await expect(link).toBeFocused();
  await page.goto('/settings');
  const setting = page.getByRole('switch', { name: 'Open sources in Mentra' });
  await expect(setting).toBeChecked();
  await setting.click();
  await expect(setting).not.toBeChecked();
  await page.goto('/chat/polish-chat');
  const disabledPopup = page.context().waitForEvent('page');
  const disabledRequest = page.context().waitForEvent('request', { predicate: request => request.url() === web(1).url && request.isNavigationRequest() });
  await link.click();
  const browserTab = await disabledPopup;
  await disabledRequest;
  await browserTab.close();
  await expect(drawer).toHaveCount(0);
});

test('Library material opens as a source tab and still links to management', async ({ page }) => {
  await workspace(page, false, true);
  await page.route('**/api/v1/documents/material-1', route => route.fulfill({ json: {
    id: 'material-1', title: 'Motion and forces', filename: 'notes.txt', context_ids: [], jobs: [], generations: [],
    versions: [{ id: 'version-1', filename: 'notes.txt', generation_id: 'generation-1', extraction_state: 'ready' }],
  } }));
  await page.route('**/versions/version-1/chunks?*', route => route.fulfill({ json: [
    { id: 'chunk', content: 'A passage from the Library.', heading_path: [], spans: [] },
  ] }));
  await page.goto('/library');
  await page.getByRole('button', { name: 'Motion and forces', exact: true }).click();
  await expect(page).toHaveURL(/\/library$/);
  const tab = page.getByRole('tabpanel', { name: 'Motion and forces' });
  await expect(tab.getByText('A passage from the Library.')).toBeVisible();
  await expect(tab.getByRole('link', { name: 'Manage material' })).toHaveAttribute('href', '/library/material-1');
});

test('the panel dropdown browses sources from earlier messages without changing chat scroll', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const fixture = await richChat(page, 'An explanation with current sources [[W1]].');
  Object.assign(fixture.items[0], { sequence: 4 });
  Object.assign(fixture.items[1], { sequence: 5, web_citations: ['W1'], web_sources: [web(1)] });
  await page.context().route('https://example.org/**', route => route.fulfill({ contentType: 'text/html', body: '<p>Source</p>' }));
  await page.route('**/api/v1/conversations/polish-chat/messages?before=4', route => route.fulfill({
    json: { items: [{ id: 'earlier-answer', conversation_id: 'polish-chat', sequence: 2, role: 'assistant',
      content: 'An earlier source', created_at: date, web_sources: [web(2)] }], has_more: false, next_cursor: null },
  }));
  await page.goto('/chat/polish-chat');
  await page.getByRole('link', { name: /Open web source W1:/ }).click();
  const panel = page.getByRole('complementary', { name: 'Side panel' });
  await panel.getByRole('button', { name: 'From this chat' }).click();
  const catalog = page.getByRole('region', { name: 'From this chat' });
  await expect(catalog.getByRole('link', { name: /Article 1/ })).toBeVisible();
  await catalog.getByRole('button', { name: 'Load earlier sources' }).click();
  await catalog.getByRole('link', { name: /Article 2/ }).click();
  await expect(panel.getByRole('tabpanel', { name: 'Article 2' })).toBeVisible();
  await expect(catalog).toHaveCount(0);
  await expect(page.getByRole('article', { name: 'Mentra response' })).toHaveCount(1);
  await panel.getByRole('button', { name: 'From this chat' }).click();
  await expect(catalog.getByRole('link', { name: /Article 2/ })).toBeVisible();
  await expect(catalog.getByRole('button', { name: 'Load earlier sources' })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(catalog).toHaveCount(0);
  await expect(panel.getByRole('tabpanel', { name: 'Article 2' })).toBeVisible();
});
