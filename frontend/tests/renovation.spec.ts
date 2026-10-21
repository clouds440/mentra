import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import type { MaterialDocument } from '../src/types/rag';

test('activity stays mounted through acknowledgement and coalesces safe feedback', async ({ page }) => {
  await workspace(page, false, true);
  let acknowledge: (() => void) | undefined;
  await page.route('**/api/v1/conversations/turns', async route => {
    await new Promise<void>(resolve => { acknowledge = resolve; }); await route.fallback();
  });
  const updates: { tool_name: string | null; status: string; step_id: string; user_message: string }[] = [
    { tool_name: 'assessment_generate', status: 'running', step_id: 'questions', user_message: 'MCP assessment_generate private trace' },
    { tool_name: 'assessment_generate', status: 'completed', step_id: 'questions', user_message: 'internal SQL complete' },
    { tool_name: 'profile_context', status: 'running', step_id: 'profile', user_message: 'private profile_context' },
    { tool_name: 'unknown_private_tool', status: 'running', step_id: 'unknown', user_message: 'private internal architecture' },
  ];
  await page.route('**/turns/*/events?*', async route => {
    const url = new URL(route.request().url());
    const turn = url.pathname.split('/').at(-2)!;
    const after = Number(url.searchParams.get('after') ?? 0);
    await route.fulfill({ contentType: 'text/event-stream', body: updates.map((item, index) => ({ ...item, schema_version: 1,
      conversation_id: 'polish-chat', turn_id: turn, attempt: 1, sequence: index + 1 }))
      .filter(item => item.sequence > after).map(item => `event: activity\ndata: ${JSON.stringify(item)}\n\n`).join('') });
  });
  await page.goto('/chat/polish-chat');
  await page.getByLabel('Ask Mentra anything').fill('Give me a practice question.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const activity = page.getByLabel('Current activity');
  await expect(activity).toContainText('Sending your message');
  await expect.poll(() => !!acknowledge).toBe(true);
  await activity.evaluate(el => {
    const probe = { element: el, logo: el.querySelector('.mentra-logo'), removed: false, labels: [] as string[] };
    (window as unknown as { activityProbe: typeof probe }).activityProbe = probe;
    new MutationObserver(() => {
      if (!probe.element.isConnected || !probe.logo?.isConnected) probe.removed = true;
      probe.labels.push(probe.element.textContent ?? '');
    }).observe(document.body, { childList: true, subtree: true });
  });
  acknowledge!();
  await expect(activity).toContainText('Preparing your practice questions');
  await expect(activity).not.toContainText(/private|SQL|MCP|profile_context|unknown_private_tool/);
  updates.push({ tool_name: null, status: 'running', step_id: 'response-stream', user_message: 'Writing your response' });
  await expect(activity).toContainText('Putting it together');
  const probe = await page.evaluate(() => {
    const value = (window as unknown as { activityProbe: { element: Element; logo: Element; removed: boolean; labels: string[] } }).activityProbe;
    return { removed: value.removed, same: document.querySelector('[aria-label="Current activity"] .mentra-logo') === value.logo, labels: value.labels };
  });
  expect(probe.removed).toBe(false); expect(probe.same).toBe(true);
  expect(probe.labels.join(' ')).not.toContain('Writing your answer');
  expect(probe.labels.join(' ')).not.toContain('Creating your practice questions'); // Burst coalesced.
  let stop: (() => void) | undefined;
  await page.route('**/turns/*/stop', async route => {
    await new Promise<void>(resolve => { stop = resolve; }); await route.fallback();
  });
  await page.getByRole('button', { name: 'Stop response', exact: true }).click();
  await expect(activity).toContainText('Stopping this response');
  await expect.poll(() => !!stop).toBe(true); stop!();
  await expect(activity).toHaveCount(0);
});

for (const long of [false, true]) test(`completed Markdown reveals in one downward sweep (${long ? 'long' : 'short'})`, async ({ page }) => {
  const state = await workspace(page, true);
  await page.goto('/chat/polish-chat');
  await expect(page.getByLabel('Current activity')).toBeVisible();
  await page.evaluate(() => {
    const samples: { formatted: boolean; raw: boolean }[] = [];
    (window as unknown as { revealSamples: typeof samples }).revealSamples = samples;
    new MutationObserver(() => {
      const answer = document.querySelector('[data-message-id="formatted-answer-41"]');
      if (answer) samples.push({ formatted: !!answer.querySelector('h2 strong'), raw: /## Reveal|\*\*ready\*\*|```/.test(answer.textContent ?? '') });
    }).observe(document.body, { childList: true, subtree: true });
  });
  state.complete('## Reveal **ready**\n\nA [formatted link](https://example.com).\n\n```python\nprint("ready")\n```\n\n' + (long ? 'A complete paragraph, already formatted.\n\n'.repeat(80) : 'A short answer.'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  const answer = page.locator('[data-message-id="formatted-answer-41"]');
  await expect(answer).toHaveClass(/chat-response-reveal/);
  const sweep = await answer.evaluate(el => {
    const animation = el.getAnimations().find(item => (item as CSSAnimation).animationName === 'chat-response-reveal')!;
    animation.pause(); animation.currentTime = 0;
    const start = getComputedStyle(el).maskPosition;
    const height = el.getBoundingClientRect().height;
    animation.currentTime = 450;
    const middle = getComputedStyle(el).maskPosition;
    animation.currentTime = 900;
    return { duration: animation.effect!.getTiming().duration, start, middle, height, finalHeight: el.getBoundingClientRect().height, finalMask: getComputedStyle(el).maskImage };
  });
  expect(sweep.duration).toBe(900); expect(sweep.start).toBe('0px 100%');
  expect(sweep.middle).not.toBe(sweep.start); expect(sweep.finalMask).toBe('none');
  expect(sweep.finalHeight).toBe(sweep.height);
  const samples = await page.evaluate(() => (window as unknown as { revealSamples: { formatted: boolean; raw: boolean }[] }).revealSamples);
  expect(samples.length).toBeGreaterThan(0); expect(samples.every(item => item.formatted && !item.raw)).toBe(true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(answer).toHaveCSS('animation-name', 'none');
  await expect(answer).toHaveCSS('mask-image', 'none');
  await page.reload();
  await expect(answer).toBeVisible(); await expect(answer).not.toHaveClass(/chat-response-reveal/);
});

for (const mobile of [false, true]) test(`chat deletion modal supports cancellation, pending state and retry (${mobile ? 'mobile' : 'desktop'})`, async ({ page }) => {
  await workspace(page, false, true);
  await page.setViewportSize({ width: mobile ? 390 : 1280, height: 844 });
  let requests = 0;
  let finish: (() => void) | undefined;
  await page.route('**/api/v1/conversations/polish-chat?*', async route => {
    if (route.request().method() !== 'DELETE') return route.fallback();
    requests++;
    await new Promise<void>(resolve => { finish = resolve; });
    await route.fulfill(requests === 1 ? { status: 500, json: { error: { message: 'Delete failed' } } } : { json: {} });
  });
  await page.goto('/chat/polish-chat');
  if (mobile) await page.getByRole('button', { name: 'Open navigation menu' }).click();
  const history = page.getByRole('region', { name: 'Conversation history' });
  const trigger = history.getByRole('button', { name: /^Actions for / });
  await trigger.focus(); await trigger.click(); await page.getByRole('menuitem', {name:'Delete',exact:true}).click();
  const dialog = page.getByRole('dialog', { name: 'Delete chat?' });
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0); await expect(trigger).toBeFocused();
  expect(requests).toBe(0);
  await trigger.click(); await page.getByRole('menuitem', {name:'Delete',exact:true}).click();
  const remove = dialog.getByRole('button', { name: 'Delete chat', exact: true });
  await remove.click();
  await expect.poll(() => requests).toBe(1);
  await expect(remove).toHaveAttribute('aria-busy', 'true');
  await expect(remove.locator('svg')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  await page.keyboard.press('Escape'); await expect(dialog).toBeVisible();
  finish!();
  await expect(dialog.getByRole('alert')).toContainText('Could not delete');
  await expect(remove).toBeEnabled();
  await remove.click(); await expect.poll(() => requests).toBe(2); finish!();
  await expect(dialog).toHaveCount(0); await expect(page).toHaveURL(/\/$/);
});

test('New Chat handoff preserves the first editable draft', async ({ page }) => {
  await workspace(page, false, true);
  await page.goto('/chat/polish-chat');
  await page.getByLabel('Ask Mentra anything').fill('Old draft');
  await page.getByRole('button', { name: 'Start a new chat' }).click();
  const composer = page.getByLabel('Ask Mentra anything');
  await composer.fill('First draft after New Chat');
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page).toHaveURL(/\/$/);
  await expect(composer).toHaveValue('First draft after New Chat');
});

test('guest entry does not download unrelated workspace or Markdown chunks', async ({ page }) => {
  const scripts: string[] = [];
  page.on('request', request => { if (request.resourceType() === 'script') scripts.push(new URL(request.url()).pathname); });
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401, json: { error: { code: 'AUTHENTICATION_FAILED' } } }));
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  expect(scripts.filter(path => /\/(ChatPage|LibraryPage|AssessmentWorkspace|MarkdownContent|OnboardingPage)-/.test(path))).toEqual([]);
});

test.describe('touch controls', () => {
  test.use({ hasTouch: true, isMobile: true });
  test('composer icons keep small glyphs and usable touch targets', async ({ page }) => {
    await workspace(page, false, true);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/chat/polish-chat');
    for (const name of ['Record voice message', 'Send message']) {
      const bounds = await page.getByRole('button', { name, exact: true }).boundingBox();
      expect(bounds!.width).toBeGreaterThanOrEqual(44); expect(bounds!.height).toBeGreaterThanOrEqual(44);
    }
    await page.getByLabel('Upload chat files').setInputFiles({ name: 'touch.txt', mimeType: 'text/plain', buffer: Buffer.from('Touch target fixture') });
    const remove = page.getByRole('button', { name: 'Remove touch.txt' });
    const bounds = await remove.boundingBox(); expect(bounds!.width).toBeGreaterThanOrEqual(44); expect(bounds!.height).toBeGreaterThanOrEqual(44);
    await remove.tap(); await expect(page.getByLabel('Attached files')).toHaveCount(0);
  });
});

test('mobile navigation is modal, restores focus, and retains history after desktop collapse', async ({ page }, info) => {
  await workspace(page, false, true);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/library');
  await page.getByRole('button', { name: 'Collapse sidebar' }).click();
  await page.setViewportSize({ width: 390, height: 568 });
  const opener = page.getByRole('button', { name: 'Open navigation menu' });
  await opener.click();
  const navigation = page.getByRole('dialog', { name: 'Main navigation' });
  await expect(navigation).toBeVisible();
  await expect(navigation.getByRole('region', { name: 'Conversation history' })).toBeVisible();
  expect(await page.locator('#workspace-content').evaluate(node => (node as HTMLElement).inert)).toBe(true);
  await navigation.getByRole('button', { name: /Account menu/ }).click();
  await expect(navigation.getByLabel('Account settings')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(navigation.getByLabel('Account settings')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await info.attach('navigation-focus.json', { body: JSON.stringify(await page.evaluate(() => ({ active: document.activeElement?.outerHTML, contentInert: document.getElementById('workspace-content')?.inert, sidebarInert: document.querySelector('aside')?.inert, role: document.querySelector('aside')?.getAttribute('role') }))), contentType: 'application/json' });
  await expect(opener).toBeFocused();
  expect(await page.getByLabel('Main navigation').evaluate(node => (node as HTMLElement).inert)).toBe(true);
  expect(await page.locator('#workspace-content').evaluate(node => (node as HTMLElement).inert)).toBe(false);
  await opener.click();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await page.locator('#workspace-content').evaluate(node => (node as HTMLElement).inert)).toBe(false);
});

test('shared tabs preserve assessment drafts, URL history and keyboard focus', async ({ page }) => {
  await workspace(page, false, true);
  await page.goto('/assessments?tab=create');
  await page.getByLabel('Topic', { exact: true }).fill('A draft to preserve');
  const create = page.getByRole('tab', { name: 'Create new' });
  await create.focus(); await create.press('Home');
  await expect(page.getByRole('tab', { name: 'Assessments', exact: true })).toBeFocused();
  await expect(page).not.toHaveURL(/tab=create/);
  await page.goBack();
  await expect(page.getByLabel('Topic', { exact: true })).toHaveValue('A draft to preserve');
  await create.focus(); await create.press('Home'); await page.getByRole('tab', { name: 'Assessments', exact: true }).press('End');
  await expect(create).toBeFocused();
  await expect(page.getByLabel('Topic', { exact: true })).toHaveValue('A draft to preserve');
});

test('relevant writes keep understanding rows and coalesce invalidation events', async ({ page }) => {
  await workspace(page, false, true);
  let requests = 0;
  await page.route('**/api/v1/learning/page*', async route => {
    requests++;
    await new Promise(resolve => setTimeout(resolve, 100));
    await route.fallback();
  });
  await page.goto('/progress');
  const row = page.getByRole('row').filter({ hasText: 'Forces' });
  await expect(row).toBeVisible();
  const count = requests;
  await page.evaluate(() => { const changes = new BroadcastChannel('mentra-pages-polish-user'); changes.postMessage(['learning']); changes.postMessage(['learning']); changes.close(); });
  await expect(row).toBeVisible();
  await expect.poll(() => requests).toBe(count + 1);
  await expect(row).toBeVisible();
});

test('reduced motion and touch-sized targets retain compact desktop geometry', async ({ page }) => {
  await workspace(page, false, true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1440, height: 800 });
  await page.goto('/library');
  const add = page.getByRole('button', { name: 'Add material', exact: true });
  expect((await add.boundingBox())!.height).toBeLessThanOrEqual(40);
  await add.click();
  await expect(page.getByRole('heading', { name: 'Add material' })).toBeVisible();
  expect(await page.locator('main').evaluate(node => getComputedStyle(node).transitionDuration)).toBe('1e-05s');
});

test('material refresh protects dirty details and source dialogs remain open until dismissed', async ({ page }) => {
  await workspace(page, false, true);
  let document: MaterialDocument = { id: 'material-1', title: 'Saved title', filename: 'notes.txt', context_ids: ['context-1'], archived: false, revision: 1, active_generation_id: 'generation-1', version_count: 1, versions: [{ id: 'version-1', filename: 'notes.txt', media_type: 'text/plain', size_bytes: 100, created_at: '2026-10-14T00:00:00Z' }], generations: [{ id: 'generation-1', version_id: 'version-1', state: 'READY', warnings: [], chunk_count: 0 }], jobs: [] };
  await page.route('**/api/v1/documents/material-1', route => route.fulfill({ json: document }));
  await page.goto('/library/material-1');
  await page.getByLabel('Title', { exact: true }).fill('Unsent draft');
  document = { ...document, revision: 2, title: 'Changed elsewhere' };
  await page.evaluate(() => { const changes = new BroadcastChannel('mentra-pages-polish-user'); changes.postMessage(['documents']); changes.close(); });
  await expect(page.getByRole('alert')).toContainText('Your draft is preserved');
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue('Unsent draft');
  await expect(page.getByRole('button', { name: 'Save material details' })).toBeDisabled();
  await page.getByRole('button', { name: 'Reload saved details' }).click();
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue('Changed elsewhere');
  const source = page.getByRole('button', { name: 'Open source version' });
  await source.click();
  const dialog = page.getByRole('dialog', { name: 'Source: Changed elsewhere' });
  await expect(dialog.getByText('No extracted passages are available', { exact: false })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(source).toBeFocused();
});
