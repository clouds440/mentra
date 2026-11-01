import { expect, test, type Page } from '@playwright/test';
import { richChat, trackRichRenders } from './renovation-rich-fixtures';

const image = (name: string) => `![${name}](https://images.example.org/${name}.svg "${name} caption")`;
async function images(page: Page) {
  await page.route('https://images.example.org/**', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="600" viewBox="0 0 900 600"><circle cx="450" cy="300" r="180" fill="#62b6a1"/><circle cx="390" cy="250" r="85" fill="#f6cb75"/><path d="M160 450L740 150" stroke="#628ac2" stroke-width="26" stroke-linecap="round"/></svg>' }));
}
for (const width of [390, 1280]) test(`image citations and source anchors stay in the reel at ${width}px`, async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.setViewportSize({ width, height: 900 }); await images(page);
  await page.route('https://example.org/favicon.ico', route => route.abort());
  const fixture = await richChat(page, `${image('First')} [[W1]]\n\n${image('Second')}\n\n[[W2]]\n\n[Image source](https://example.org/second)\n\n${image('Third')} [[W3]]\n\nThis explanation separates the next image and keeps its own citation [[W2]].\n\n${image('Fourth')} [[W4]]`);
  Object.assign(fixture.items[1], {
    web_citations: ['W1', 'W2', 'W3', 'W4'],
    web_sources: [1, 2, 3, 4].map(index => ({ token: `W${index}`, title: `Source ${index}`, url: `https://example.org/source/${index}`, domain: 'example.org', favicon_url: 'https://example.org/favicon.ico', excerpt: 'Fixture evidence', searched_at: '2026-11-01T00:00:00Z' })),
  });
  await page.goto('/chat/polish-chat');
  const reel = page.locator('.image-reel');
  await expect(reel).toHaveCount(1);
  await expect(reel.locator('figure')).toHaveCount(3);
  await expect(page.locator('figure.markdown-image')).toHaveCount(4);
  const captions = reel.locator('figcaption');
  for (const [index, token] of ['W1', 'W2', 'W3'].entries()) {
    await expect(captions.nth(index).getByRole('link', { name: new RegExp(`Open web source ${token}:`) })).toHaveAttribute('href', `https://example.org/source/${index + 1}`);
  }
  await expect(captions.nth(1).getByRole('link', { name: 'Image source', exact: true })).toHaveAttribute('href', 'https://example.org/second');
  await expect(page.locator('p').filter({ hasText: 'This explanation separates' }).getByRole('link')).toHaveCount(1);
  await expect(page.locator('.image-open a, .image-open button')).toHaveCount(0);
  await page.getByRole('button', { name: 'Expand image: Second caption' }).click();
  await expect(page.getByRole('dialog').getByRole('status')).toHaveText('Image 2 of 4');
  await expect(page.getByRole('dialog').getByRole('link', { name: 'Source', exact: true })).toHaveAttribute('href', 'https://example.org/second');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Copy response', exact: true }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain('[[W1]]'); expect(copied).toContain('Image source (https://example.org/second)');
  expect(copied).toContain('This explanation separates');
});

test('reference source anchors bridge images while code and actual prose stay separate', async ({ page }) => {
  await images(page);
  await richChat(page, `${image('First')} [[W1]](https://example.org/first)\n\n${image('Second')} [Source][origin]\n\n\`[[W1]]\` is code, not an image reference.\n\n${image('Third')}\n\n${image('Fourth')}\n\n[origin]: https://example.org/second`);
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.image-reel')).toHaveCount(2);
  await expect(page.locator('.image-reel').first().locator('figcaption').first().getByRole('link')).toHaveAttribute('href', 'https://example.org/first');
  await expect(page.locator('.image-reel').first().getByRole('link', { name: 'Source', exact: true })).toHaveAttribute('href', 'https://example.org/second');
  await expect(page.locator('p').filter({ hasText: 'is code, not an image reference' }).locator('code')).toHaveText('[[W1]]');
});
for (const width of [390, 1280]) for (const theme of ['light', 'dark']) test(`background-free responsive image reel at ${width}px in ${theme}`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 900 });
  await page.addInitScript(theme => localStorage.setItem('mentra-theme', theme), theme);
  await images(page);
  await richChat(page, `## A closer look\n\n${image('First')}\n\n${image('Second')}\n${image('Third')}\n\nImages stay together; this explanation separates the next one.\n\n${image('Fourth')}`);
  await page.goto('/chat/polish-chat');
  const reel = page.getByRole('region', { name: 'Image collection' });
  await expect(reel).toHaveCount(1);
  await reel.hover(); await page.mouse.wheel(0, -10000); await reel.scrollIntoViewIfNeeded();
  const track = reel.getByRole('region', { name: 'Scrollable images' });
  await expect(track.locator('figure')).toHaveCount(3);
  await expect(page.locator('figure.markdown-image')).toHaveCount(4);
  const layout = await track.evaluate(el => ({ viewport: el.clientWidth, content: el.scrollWidth, item: el.querySelector('figure')!.getBoundingClientRect().width }));
  expect(layout.content).toBeGreaterThan(layout.viewport);
  expect(layout.viewport / layout.item).toBeGreaterThan(width === 390 ? 1 : 2);
  for (const selector of ['figure', 'figcaption', '.image-open', 'img']) await expect(track.locator(selector).first()).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await expect(reel.getByRole('button', { name: 'Scroll images right' })).toBeEnabled();
  await reel.getByRole('button', { name: 'Scroll images right' }).click();
  await expect.poll(() => track.evaluate(el => el.scrollLeft)).toBeGreaterThan(10);
  await expect(reel.getByRole('button', { name: 'Scroll images left' })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await track.evaluate(el => { el.scrollLeft = 0; });
  await page.screenshot({ path: info.outputPath(`image-reel-${width}-${theme}.png`), fullPage: true });
});

test('one viewer navigates across text breaks, keeps labels and restores the original opener', async ({ page }, info) => {
  await images(page);
  await richChat(page, `${image('First')}\n\n${image('Second')}\n\nA separate explanation.\n\n${image('Third')}`);
  await page.goto('/chat/polish-chat');
  const opener = page.getByRole('button', { name: 'Expand image: Second caption' });
  await opener.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('status')).toHaveText('Image 2 of 3');
  await dialog.getByRole('button', { name: 'Next image', exact: true }).click();
  await expect(dialog.getByRole('img')).toHaveAttribute('alt', 'Third');
  await expect(dialog.locator('.image-viewer-caption')).toHaveText('Third caption');
  expect(await dialog.boundingBox()).toMatchObject({ x: 0, y: 0, ...page.viewportSize()! });
  await page.screenshot({ path: info.outputPath('image-viewer.png') });
  await expect(dialog.getByRole('button', { name: 'Next image', exact: true })).toBeDisabled();
  await page.keyboard.press('ArrowLeft'); await expect(dialog.getByRole('status')).toHaveText('Image 2 of 3');
  await page.keyboard.press('Home'); await expect(dialog.getByRole('status')).toHaveText('Image 1 of 3');
  await expect(dialog.getByRole('button', { name: 'Previous image', exact: true })).toBeDisabled();
  await page.keyboard.press('End'); await expect(dialog.getByRole('status')).toHaveText('Image 3 of 3');
  await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(opener).toBeFocused();
});

test('text selection skips image highlighting and navigation never selects or drags images', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await images(page);
  await richChat(page, `Text before the pictures.\n\n${image('First')} ${image('Second')}\n\nText after the pictures.`);
  await page.goto('/chat/polish-chat');
  const photo = page.locator('.markdown-image img').first();
  await expect.poll(() => photo.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(900);
  await photo.scrollIntoViewIfNeeded();
  const original = await photo.screenshot();
  // Select across the reel as a reader would, keeping ordinary prose selectable.
  const before = (await page.getByText('Text before the pictures.', { exact: true }).boundingBox())!;
  const after = (await page.getByText('Text after the pictures.', { exact: true }).boundingBox())!;
  await page.mouse.move(before.x, before.y + before.height / 2);
  await page.mouse.down();
  await page.mouse.move(after.x + after.width, after.y + after.height / 2, { steps: 12 });
  await page.mouse.up();
  expect(await page.evaluate(() => getSelection()?.toString())).toContain('Text after the pictures.');
  expect(await photo.screenshot()).toEqual(original);
  await page.evaluate(() => getSelection()?.removeAllRanges());
  await page.evaluate(() => {
    (window as any).imageDragStarts = 0;
    document.addEventListener('dragstart', () => (window as any).imageDragStarts++);
  });
  const box = (await photo.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 20, { steps: 8 });
  await page.mouse.up();
  expect(await page.evaluate(() => (window as any).imageDragStarts)).toBe(0);
  const opener = page.getByRole('button', { name: 'Expand image: First caption' });
  if (await page.getByRole('dialog').count() === 0) await opener.click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('img').dblclick();
  await dialog.getByRole('button', { name: 'Next image', exact: true }).click();
  await dialog.getByRole('button', { name: 'Previous image', exact: true }).click();
  await expect(dialog.getByRole('img')).toHaveAttribute('alt', 'First');
  expect(await page.evaluate(() => getSelection()?.toString())).toBe('');
  const expanded = dialog.getByRole('img');
  const preview = await expanded.screenshot();
  await expanded.dblclick();
  expect(await expanded.screenshot()).toEqual(preview);
  await dialog.locator('.image-viewer-caption').dblclick();
  expect(await page.evaluate(() => getSelection()?.toString())).toContain('caption');
});

test('reference and linked images group automatically, unsafe URLs stay blocked, failed images remain navigable', async ({ page }) => {
  await images(page);
  await page.route('https://images.example.org/broken.svg', route => route.abort());
  const unsafe: string[] = []; page.on('request', request => { if (request.url().includes('/private.png')) unsafe.push(request.url()); });
  await richChat(page, '![Ref][photo]\n\n[![Linked](https://images.example.org/linked.svg "Linked label")](https://example.org/source)\n\n![Broken](https://images.example.org/broken.svg)\n\n![Blocked](http://localhost/private.png)\n\n[photo]: https://images.example.org/ref.svg "Reference label"');
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.image-reel')).toHaveCount(1);
  await expect(page.locator('figure.markdown-image')).toHaveCount(4);
  await expect(page.getByRole('link', { name: 'Source', exact: true })).toHaveAttribute('href', 'https://example.org/source');
  await page.getByRole('button', { name: 'Expand image: Reference label' }).click();
  const dialog = page.getByRole('dialog'); await page.keyboard.press('End');
  await expect(dialog.getByText('Image unavailable')).toBeVisible(); expect(unsafe).toEqual([]);
  await page.keyboard.press('ArrowLeft'); await expect(dialog.getByText('Image unavailable')).toBeVisible();
  await page.keyboard.press('ArrowLeft'); await expect(dialog.getByRole('img')).toHaveAttribute('alt', 'Linked');
  await expect(dialog.getByRole('link', { name: 'Source' })).toHaveAttribute('href', 'https://example.org/source');
  await expect(page.locator('p figure, a button, button button')).toHaveCount(0);
});

test('gallery navigation, scrolling and typing do not reparse completed Markdown', async ({ page }) => {
  await trackRichRenders(page, ['ChatMessage', 'MarkdownContent']);
  await images(page); await richChat(page, `${image('First')} ${image('Second')}\n\nA gap.\n\n${image('Third')}`);
  await page.goto('/chat/polish-chat'); await expect(page.locator('figure.markdown-image')).toHaveCount(3);
  await page.evaluate(() => { const counts = (window as any).richRenderProfile.counts; for (const key of Object.keys(counts)) counts[key] = 0; });
  await page.getByRole('button', { name: 'Expand image: First caption' }).click();
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight'); await page.keyboard.press('Escape');
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).pressSequentially('Keep the images in view', { delay: 10 });
  const counts = await page.evaluate(() => (window as any).richRenderProfile.counts);
  expect(counts).toEqual({ ChatMessage: 0, MarkdownContent: 0 });
});

test('inline prose separates reels, touch gestures navigate, and copy preserves captions and paragraphs', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']); await images(page);
  await richChat(page, `Before.\n\n${image('First')} actual explanation ${image('Second')}\n\nAfter.`);
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.image-reel')).toHaveCount(0);
  await page.getByRole('button', { name: 'Expand image: First caption' }).click();
  const stage = page.getByRole('group', { name: 'Image preview' });
  await stage.dispatchEvent('pointerdown', { pointerId: 1, pointerType: 'touch', isPrimary: true, clientX: 250, clientY: 200 });
  await stage.dispatchEvent('pointerup', { pointerId: 1, pointerType: 'touch', isPrimary: true, clientX: 100, clientY: 205 });
  await expect(page.getByRole('dialog').getByRole('status')).toHaveText('Image 2 of 2');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Copy response', exact: true }).click();
  const copied = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n?/g, '\n');
  expect(copied).toContain('Before.\n\n'); expect(copied).toContain('First caption'); expect(copied).toContain('Second caption'); expect(copied).toContain('\n\nAfter.');
  expect(copied).not.toContain('mentra-image'); expect(copied).not.toContain('"images"');
});

for (const width of [390, 1280]) test(`quiet interactive surfaces preserve input behavior at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 950 }); await images(page);
  const content = '## Explore at your pace\n\n:::callout{title="A useful connection" tone="info"}\nA small change can make a large difference.\n:::\n\n:::details{title="Why it works"}\nFollow the relationship one step at a time.\n:::\n\n```recharts\n{"type":"BarChart","title":"An illustrative comparison","xKey":"topic","enableControls":true,"data":[{"topic":"A","value":3},{"topic":"B","value":5}],"series":[{"dataKey":"value","color":"green"}]}\n```';
  const choice = { id: 'polish-choice', kind: 'single_choice', question: 'What would you like to explore?', selected: [], submitted_turn_id: null, options: [{ id: 'a', label: 'Understand the main idea' }, { id: 'custom', label: 'A topic of my own', input: { kind: 'short_text', label: 'Your topic', required: true } }] };
  const bars = { id: 'polish-bars', kind: 'value_bars', question: 'A quick comparison', bars: [{ label: 'Concept A', value: 3, max: 5 }, { label: 'Concept B', value: 4, max: 5 }] };
  await richChat(page, content, [choice, bars]); await page.goto('/chat/polish-chat');
  const card = page.getByRole('region', { name: 'Interactive question' });
  await card.getByRole('radio', { name: 'A topic of my own' }).check();
  await card.getByRole('textbox', { name: 'Your topic' }).fill('Learning through pictures');
  await expect(card.getByRole('button', { name: 'Submit selection' })).toBeEnabled();
  for (const surface of await page.locator('.interactive-surface').all()) await expect(surface).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await card.screenshot({ path: info.outputPath(`interactive-form-${width}.png`) });
  const chart = page.locator('.recharts-figure'); await chart.scrollIntoViewIfNeeded();
  await expect(chart.locator('.recharts-wrapper')).toBeVisible();
  await chart.screenshot({ path: info.outputPath(`interactive-chart-${width}.png`) });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('a tall image fits the fullscreen viewer without covering its caption or controls', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 850 });
  await page.route('https://images.example.org/**', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="1800"><rect x="100" y="100" width="400" height="1600" rx="100" fill="#62b6a1"/></svg>' }));
  await richChat(page, image('Tall')); await page.goto('/chat/polish-chat');
  await page.getByRole('button', { name: 'Expand image: Tall caption' }).click();
  const dialog = page.getByRole('dialog');
  const photo = dialog.getByRole('img'); await expect(photo).toBeVisible();
  await expect.poll(() => photo.evaluate(node => (node as HTMLImageElement).naturalHeight)).toBe(1800);
  const picture = (await photo.boundingBox())!, stage = (await dialog.getByRole('group', { name: 'Image preview' }).boundingBox())!;
  expect(picture.y).toBeGreaterThanOrEqual(stage.y); expect(picture.y + picture.height).toBeLessThanOrEqual(stage.y + stage.height + 1);
  expect(picture.width / picture.height).toBeCloseTo(1 / 3, 2);
  await expect(dialog.locator('.image-viewer-caption')).toBeInViewport();
  await expect(dialog.getByRole('button', { name: 'Close image viewer' })).toBeInViewport();
});
