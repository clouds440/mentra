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

test('opening the desktop panel animates without shifting the workspace', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await citations(page);
  await page.goto('/chat/polish-chat');
  const trigger = page.getByRole('button', { name: 'Open side panel', exact: true });
  const openAndMeasure = () => trigger.evaluate(async button => {
    const panel = document.getElementById('workspace-side-panel')!;
    const sidebar = document.getElementById('main-sidebar')!;
    const measure = () => ({ width: panel.getBoundingClientRect().width, sidebarX: sidebar.getBoundingClientRect().x,
      workspaceScroll: panel.parentElement!.scrollLeft });
    const before = measure();
    const frames = [];
    button.click();
    const until = performance.now() + 250;
    do {
      await new Promise(requestAnimationFrame);
      frames.push(measure());
    } while (performance.now() < until);
    return { before, frames };
  });
  for (const reopening of [false, true]) {
    if (reopening) {
      await page.getByRole('button', { name: 'Hide side panel', exact: true }).click();
      await expect(page.locator('#workspace-side-panel')).toHaveCSS('width', '0px');
    }
    const { before, frames } = await openAndMeasure();
    const finalWidth = frames.at(-1)!.width;
    expect(finalWidth).toBeGreaterThan(300);
    expect(frames.some(frame => frame.width > 0 && frame.width < finalWidth)).toBe(true);
    expect(frames.every(frame => frame.sidebarX === before.sidebarX && frame.workspaceScroll === 0)).toBe(true);
  }
  await expect(page.getByRole('tab', { name: 'Chat sources' })).toBeFocused();
});

test('sources open new tabs, retain previews, resize and scroll without losing chat position', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ colorScheme: null });
  await citations(page);
  await page.goto('/chat/polish-chat');
  const trigger = page.getByRole('button', { name: 'Open side panel', exact: true });
  await expect(trigger.locator('svg')).toHaveClass(/lucide-panel-right/);
  expect((await trigger.boundingBox())!.x).toBeGreaterThan((await page.getByRole('link', { name: 'Notifications' }).boundingBox())!.x);
  await trigger.click();
  const catalogTab = page.getByRole('tabpanel', { name: 'Chat sources' });
  await expect(catalogTab.getByRole('link', { name: /Article 1/ })).toBeVisible();
  await expect(catalogTab.getByText('Publisher excerpt 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close tab: Chat sources' }).click();
  const open = page.getByRole('button', { name: 'Web sources (8)', exact: true });
  await expect(open).toHaveAttribute('title', 'Open in side panel');
  await open.click();
  const panel = page.getByRole('complementary', { name: 'Side panel' });
  await expect(panel).toHaveCSS('transition-property', 'width, visibility');
  const list = panel.getByRole('tabpanel', { name: 'Web sources' });
  await expect(list.getByText('Publisher excerpt 1', { exact: true })).toBeVisible();
  await expect(panel.getByRole('tab', { name: 'Web sources' }).locator('svg')).toHaveClass(/lucide-list-tree/);
  const first = list.getByRole('link', { name: /Open web source W1:/ });
  await expect(first).toHaveAttribute('href', web(1).url);
  await expect(first).toHaveAttribute('target', '_blank');
  await first.click();
  const preview = panel.getByRole('tabpanel', { name: 'Article 1' });
  await expect(preview.getByRole('link', { name: 'Open in browser' })).toHaveAttribute('href', web(1).url);
  const toolbar = preview.locator('.workspace-web-toolbar');
  await expect(toolbar.locator('button, a')).toHaveCount(5);
  expect(await toolbar.locator('button, a').evaluateAll(controls => controls.map(control => control.getAttribute('aria-label'))))
    .toEqual(['Back', 'Forward', 'Reader', 'Open in browser', 'Pin source']);
  await expect(toolbar.getByText('example.org', { exact: true })).toBeVisible();
  await expect(toolbar.getByText('Open in browser', { exact: true })).toBeHidden();
  await expect(toolbar.getByText('Reader', { exact: true })).toBeHidden();
  await expect(preview.locator('iframe')).toHaveAttribute('sandbox', 'allow-scripts');
  const publisher = preview.frameLocator('iframe').getByRole('heading', { name: 'Publisher preview' });
  await expect(publisher).toBeVisible();
  for (const [theme, color] of [['dark', 'rgb(255, 255, 255)'], ['light', 'rgb(0, 0, 0)']]) {
    await page.evaluate(next => window.dispatchEvent(new StorageEvent('storage', {
      key: 'mentra-theme', newValue: next, storageArea: localStorage,
    })), theme);
    await expect(publisher).toHaveCSS('color', color);
    const bell = page.getByRole('link', { name: 'Notifications' });
    const bellColor = await bell.locator('svg').evaluate(icon => getComputedStyle(icon).color);
    await bell.hover();
    const bellHover = await bell.evaluate(control => getComputedStyle(control).backgroundColor);
    for (const name of ['Collapse sidebar', 'Hide side panel']) {
      const control = page.getByRole('button', { name, exact: true });
      await expect(control.locator('svg')).toHaveCSS('color', bellColor);
      await control.hover();
      await expect(control).toHaveCSS('background-color', bellHover);
    }
  }
  await expect(preview.getByText('Publisher excerpt 1')).toHaveCount(0);
  await preview.getByRole('button', { name: 'Back', exact: true }).click();
  const returned = panel.getByRole('tabpanel').filter({ has: page.getByRole('button', { name: 'Forward', exact: true }) });
  await expect(returned).toHaveAccessibleName('Web sources');
  await returned.getByRole('button', { name: 'Forward', exact: true }).click();
  await expect(preview).toBeVisible();
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
  const chat = (await page.getByRole('log', { name: 'Conversation' }).boundingBox())!;
  const shell = (await panel.locator('.workspace-panel-shell').boundingBox())!;
  expect(grip.width).toBe(6);
  expect(grip.x).toBeGreaterThanOrEqual(chat.x + chat.width);
  expect(shell.x).toBeGreaterThanOrEqual(grip.x + grip.width);
  await page.mouse.move(chat.x + chat.width - 1, grip.y + 80);
  await page.mouse.down();
  await expect(panel).toHaveAttribute('data-resizing', 'false');
  await page.mouse.up();
  const width = (await panel.boundingBox())!.width;
  await page.mouse.move(grip.x + grip.width / 2, grip.y + 80);
  await page.mouse.down();
  await page.mouse.move(grip.x + grip.width / 2 - 72, grip.y + 80, { steps: 5 });
  await page.mouse.up();
  expect((await panel.boundingBox())!.width).toBeGreaterThan(width + 50);
  const wideToolbar = panel.getByRole('tabpanel', { name: 'Article 6' }).locator('.workspace-web-toolbar');
  await expect(wideToolbar.getByText('Open in browser', { exact: true })).toBeVisible();
  await expect(wideToolbar.getByText('Reader', { exact: true })).toBeVisible();
  await handle.press('Home');
  await expect(handle).toHaveAttribute('aria-valuenow', '340');
  await expect(panel).toHaveCSS('width', '340px');
  await expect(wideToolbar.getByText('Reader', { exact: true })).toBeHidden();
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
  await panel.getByRole('button', { name: 'Browse', exact: true }).click();
  const catalog = page.getByRole('region', { name: 'Browse sources' });
  await expect(panel.getByRole('button', { name: 'Browse', exact: true }).locator('svg')).toHaveCount(1);
  const fromChat = catalog.getByRole('tab', { name: 'From this chat' });
  const pinned = catalog.getByRole('tab', { name: 'Pinned' });
  await pinned.click();
  await expect(pinned).toHaveAttribute('aria-selected', 'true');
  await catalog.getByText('Pin a source to keep it here across chats.').click();
  await expect(catalog).toBeVisible();
  await fromChat.click();
  await expect(catalog.getByRole('link', { name: /Article 1/ })).toBeVisible();
  await expect(catalog.getByText('Publisher excerpt 1', { exact: true })).toHaveCount(0);
  await catalog.getByRole('button', { name: 'Load earlier sources' }).click();
  const earlier = catalog.getByRole('link', { name: /Article 2/ });
  await expect(earlier).toBeVisible();
  await expect(catalog.getByText('Publisher excerpt 2', { exact: true })).toHaveCount(0);
  await earlier.click();
  await expect(panel.getByRole('tabpanel', { name: 'Article 2' })).toBeVisible();
  await expect(catalog).toHaveCount(0);
  await expect(page.getByRole('article', { name: 'Mentra response' })).toHaveCount(1);
  await panel.getByRole('button', { name: 'Browse', exact: true }).click();
  await expect(catalog.getByRole('link', { name: /Article 2/ })).toBeVisible();
  await expect(catalog.getByRole('button', { name: 'Load earlier sources' })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(catalog).toHaveCount(0);
  await expect(panel.getByRole('tabpanel', { name: 'Article 2' })).toBeVisible();
  await panel.getByRole('button', { name: 'Browse', exact: true }).click();
  await expect(catalog).toBeVisible();
  await panel.getByRole('tab', { name: 'Article 2', exact: true }).click();
  await expect(catalog).toHaveCount(0);
});

test('quotes only the selected text from chat and keeps it as an annotation after sending', async ({ page }) => {
  const fixture = await richChat(page, 'First line. Quote this part. Leave this out.');
  await page.goto('/chat/polish-chat');
  const answer = page.getByText('First line. Quote this part. Leave this out.', { exact: true });
  await answer.evaluate(node => {
    const range = document.createRange();
    range.setStart(node.firstChild!, 12);
    range.setEnd(node.firstChild!, 28);
    const selection = window.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
  });
  await page.getByRole('button', { name: 'Send to chat', exact: true }).click();
  const draft = page.getByRole('list', { name: 'Draft excerpts' });
  await expect(draft).toContainText('Quote this part.');
  await expect(draft).not.toContainText('Leave this out.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect.poll(() => fixture.submissions.length).toBe(1);
  expect(fixture.submissions[0]).toMatchObject({ content: '', source_annotations: [
    { source: { kind: 'chat', title: 'Mentra response' }, text: 'Quote this part.' },
  ] });
  expect((fixture.submissions[0].source_annotations as { source: object }[])[0].source).toEqual({ kind: 'chat', title: 'Mentra response' });
  await expect(page.getByRole('list', { name: 'Referenced excerpts' })).toContainText('Quote this part.');
  await expect(draft).toHaveCount(0);
});

test('Browse keeps account pins across reloads and Reader follows independent tab history', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await citations(page);
  const saved: { id: string; source: { title: string } }[] = [];
  await page.route('**/api/v1/workspace/pins', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: saved });
    saved.push({ id: 'pin-1', source: route.request().postDataJSON() });
    return route.fulfill({ json: saved.at(-1) });
  });
  await page.route('**/api/v1/workspace/pins/pin-1', route => {
    saved.length = 0;
    return route.fulfill({ status: 204 });
  });
  await page.route('**/api/v1/web/reader', route => route.fulfill({ json: { url: web(2).url,
    blocks: ['An exact reader excerpt.'], links: [{ url: web(3).url, title: 'Related page' }] } }));
  await page.goto('/chat/polish-chat');
  const panel = page.getByRole('complementary', { name: 'Side panel' });
  await page.getByRole('link', { name: /Open web source W1:/ }).click();
  await page.getByRole('link', { name: /Open web source W2:/ }).click();
  const blocked = panel.getByRole('tabpanel', { name: 'Article 2' });
  await blocked.getByRole('button', { name: 'Reader' }).click();
  await blocked.getByText('An exact reader excerpt.').evaluate(node => {
    const range = document.createRange();
    range.selectNodeContents(node);
    window.getSelection()!.addRange(range);
  });
  await page.getByRole('button', { name: 'Send to chat', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Draft excerpts' })).toContainText('An exact reader excerpt.');
  await page.getByRole('button', { name: 'Remove excerpt 1' }).click();
  await expect(page.getByRole('list', { name: 'Draft excerpts' })).toHaveCount(0);
  await blocked.getByRole('button', { name: 'Pin source', exact: true }).click();
  await expect(blocked.getByRole('button', { name: 'Unpin source', exact: true })).toBeEnabled();
  await blocked.getByRole('link', { name: 'Related page' }).click();
  const related = panel.getByRole('tabpanel', { name: 'Related page' });
  await expect(related).toBeVisible();
  await expect(panel.getByRole('tab')).toHaveCount(2);
  await related.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(blocked.getByText('An exact reader excerpt.')).toBeVisible();
  await panel.getByRole('tab', { name: 'Article 1' }).click();
  await expect(panel.getByRole('tabpanel', { name: 'Article 1' }).getByRole('button', { name: 'Forward', exact: true })).toBeDisabled();
  await panel.getByRole('tab', { name: 'Article 2' }).click();
  await blocked.getByRole('button', { name: 'Forward', exact: true }).click();
  await expect(related).toBeVisible();

  await page.goto('/library');
  await page.getByRole('button', { name: 'Open side panel', exact: true }).click();
  await panel.getByRole('button', { name: 'Browse', exact: true }).click();
  const browse = page.getByRole('region', { name: 'Browse sources' });
  await expect(browse.getByRole('tab', { name: 'Pinned', exact: true })).toHaveAttribute('aria-selected', 'true');
  await browse.getByRole('button', { name: 'Article 2', exact: true }).click();
  await expect(blocked).toBeVisible();
  await blocked.getByRole('button', { name: 'Unpin source', exact: true }).click();
  await expect(blocked.getByRole('button', { name: 'Pin source', exact: true })).toBeEnabled();
  expect(saved).toHaveLength(0);
});
