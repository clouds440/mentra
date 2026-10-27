import { expect, test, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { chooseOption } from './select-helpers';

const choice = { id: 'choice-rich', kind: 'single_choice', question: 'Which topic?', selected: [], submitted_turn_id: null, options: [
  { id: 'algebra', label: 'Algebra' }, { id: 'custom', label: "I'll write my own topic", input: { kind: 'short_text', label: 'Your topic', required: true, max_length: 300 } },
] };
async function richChat(page: Page, content = '', interactions: Record<string, unknown>[] = []) {
  await workspace(page);
  const conversation = { id: 'polish-chat', title: 'Interactive examples', revision: 2, message_count: 2, selection: { mode: 'STANDARD', context_ids: [], document_ids: [] }, created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00Z' };
  const items: Record<string, unknown>[] = [{ id: 'u', conversation_id: conversation.id, sequence: 1, role: 'user', content: 'Explain this concept', created_at: conversation.created_at }, { id: 'a', conversation_id: conversation.id, sequence: 2, role: 'assistant', content, interactions, created_at: conversation.created_at }];
  let turn: Record<string, unknown> | null = null;
  const snapshot = () => ({ conversation, items, has_more: false, next_cursor: null, turn });
  await page.route('**/api/v1/conversations/polish-chat/status*', route => route.fulfill({ json: snapshot() }));
  const submissions: Record<string, unknown>[] = [];
  await page.route('**/api/v1/conversations/turns', route => {
    const body = route.request().postDataJSON(); submissions.push(body);
    const reply = body.interaction_response;
    if (reply) {
      const card = interactions.find(item => item.id === reply.interaction_id)!;
      Object.assign(card, { ...reply, submitted_turn_id: body.client_turn_id });
    }
    conversation.revision++; conversation.message_count++;
    items.push({ id: 'answer-' + conversation.message_count, conversation_id: conversation.id, sequence: conversation.message_count, role: 'user', content: body.content, created_at: conversation.created_at });
    turn = { id: body.client_turn_id, state: 'SUCCEEDED', attempt: 1, user_sequence: conversation.message_count, selection: conversation.selection, error: null };
    return route.fulfill({ json: snapshot() });
  });
  return { submissions };
}

for (const width of [375, 1280]) test(`custom topic opens inside the card and persists on ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 900 });
  const { submissions } = await richChat(page, 'Choose a topic.', [structuredClone(choice)]);
  await page.goto('/chat/polish-chat');
  const card = page.getByRole('region', { name: 'Interactive question' });
  await expect(card.getByRole('textbox')).toHaveCount(0);
  await card.getByRole('radio', { name: "I'll write my own topic" }).check();
  const input = card.getByRole('textbox', { name: 'Your topic' });
  await expect(input).toBeFocused();
  await expect(card.getByRole('button', { name: 'Submit selection' })).toBeDisabled();
  await input.fill('درخت — Database indexes');
  await card.getByRole('radio', { name: 'Algebra', exact: true }).check();
  await expect(card.getByRole('textbox')).toHaveCount(0);
  await card.getByRole('radio', { name: "I'll write my own topic" }).check();
  await expect(input).toHaveValue('درخت — Database indexes');
  await card.getByRole('button', { name: 'Submit selection' }).click();
  await expect(card.getByText('Selection submitted.')).toBeVisible();
  expect(submissions[0].interaction_response).toMatchObject({ selected: ['custom'], option_inputs: { custom: 'درخت — Database indexes' } });
  await page.reload();
  await expect(input).toHaveValue('درخت — Database indexes'); await expect(input).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: info.outputPath(`custom-topic-${width}.png`), fullPage: true });
});

test('an unconfirmed form retries the original payload without accepting edits', async ({ page }) => {
  const { submissions } = await richChat(page, 'Choose a topic.', [structuredClone(choice)]);
  let original: Record<string, unknown> | undefined;
  await page.route('**/api/v1/conversations/turns', route => { original = route.request().postDataJSON(); return route.abort('failed'); }, { times: 1 });
  await page.goto('/chat/polish-chat');
  const card = page.getByRole('region', { name: 'Interactive question' });
  await card.getByRole('radio', { name: "I'll write my own topic" }).check();
  const input = card.getByRole('textbox', { name: 'Your topic' });
  await input.fill('Original topic');
  await card.getByRole('button', { name: 'Submit selection' }).click();
  await expect(card.getByRole('button', { name: 'Retry original answer' })).toBeVisible();
  await expect(input).toBeDisabled(); await expect(input).toHaveValue('Original topic');
  await card.getByRole('button', { name: 'Retry original answer' }).click();
  await expect(card.getByText('Selection submitted.')).toBeVisible();
  expect(submissions).toHaveLength(1);
  expect(submissions[0].client_turn_id).toBe(original!.client_turn_id);
  expect(submissions[0].interaction_response).toEqual(original!.interaction_response);
  expect(submissions[0].retry).toBe(true);
});

test('nested rich blocks and small numeric scales render and copy consistently', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await richChat(page, '> ::bar{label="Small scale" value="0.00001" max="0.00002"}\n\n:color[Outer :color[inner]{tone="warning"}]{tone="success"}');
  await page.goto('/chat/polish-chat');
  const meter = page.getByRole('meter', { name: 'Small scale' });
  await expect(meter).toHaveAttribute('aria-valuenow', '0.00001');
  await expect(page.getByText('0 / 0 · 50%', { exact: false })).toHaveCount(0);
  await expect(page.locator('.rich-color .rich-color')).toHaveText('inner');
  await page.getByRole('button', { name: 'Copy response', exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('Small scale:');
});

test('a failed diagram chunk leaves the answer and composer usable', async ({ page }) => {
  await richChat(page, 'Before the diagram.\n\n```mermaid\nflowchart LR\n A --> B\n```\n\nAfter the diagram.');
  await page.route('**/assets/MermaidDiagram-*.js', route => route.abort('failed'));
  await page.goto('/chat/polish-chat');
  await expect(page.getByText('Before the diagram.', { exact: true })).toBeVisible();
  await expect(page.getByText('After the diagram.', { exact: true })).toBeVisible();
  await expect(page.getByText('This diagram could not be loaded. Its source is available below.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'This page couldn’t open' })).toHaveCount(0);
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('The conversation still works');
});

test('unknown future controls degrade locally during mixed-version delivery', async ({ page }) => {
  await richChat(page, 'The explanation remains available.', [{ id: 'future', kind: 'future_control', question: 'Future component' }]);
  await page.goto('/chat/polish-chat');
  await expect(page.getByText('The explanation remains available.', { exact: true })).toBeVisible();
  await expect(page.getByText('This interactive item is not supported by this version. You can reply in the chat instead.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Use a plain reply');
});

test('encoded diagram resource styles are rejected before rendering', async ({ page }) => {
  const external: string[] = [];
  page.on('request', request => { if (request.url().includes('tracker.invalid')) external.push(request.url()); });
  const code = String.raw`C4Context
Person(user, "Student")
UpdateElementStyle(user, $bgColor="u\72l(//tracker.invalid/image)")`;
  await richChat(page, `The answer is still readable.\n\n\`\`\`mermaid\n${code}\n\`\`\``);
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.mermaid-figure code')).toContainText('UpdateElementStyle');
  await expect(page.locator('.mermaid-svg svg')).toHaveCount(0);
  expect(external).toEqual([]);
});

test('font size changes made while chat is unmounted apply on return', async ({ page }) => {
  await richChat(page, 'A comfortable reading size.'); await page.goto('/chat/polish-chat');
  await expect(page.getByRole('article', { name: 'Mentra response' }).locator('.chat-prose')).toHaveCSS('font-size', '16px');
  await page.getByRole('link', { name: 'Library', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.evaluate(() => { localStorage.setItem('mentra-chat-font-size', 'large'); window.dispatchEvent(new StorageEvent('storage', { key: 'mentra-chat-font-size', newValue: 'large' })); });
  await page.getByRole('region', { name: 'Conversation history' }).locator('a[href="/chat/polish-chat"]').click();
  await expect(page.getByRole('article', { name: 'Mentra response' }).locator('.chat-prose')).toHaveCSS('font-size', '18px');
});

test('diagram IDs and arrow references stay valid in regular and expanded views', async ({ page }) => {
  await richChat(page, '```mermaid\nflowchart LR\n A --> A1\n A1 --> A12\n A12 --> A\n```');
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.mermaid-svg > svg')).toBeVisible();
  await page.getByRole('button', { name: 'Expand', exact: true }).click();
  await expect(page.getByRole('dialog').locator('svg')).toBeVisible();
  const missing = await page.locator('.mermaid-svg svg').evaluateAll(svgs => svgs.flatMap(svg => {
    const ids = new Set([svg.id, ...Array.from(svg.querySelectorAll('[id]')).map(node => node.id)]);
    return Array.from(svg.querySelectorAll('*')).flatMap(node => Array.from(node.attributes).flatMap(attribute =>
      Array.from(attribute.value.matchAll(/url\(\s*["']?#([^\s)'"  ]+)["']?\s*\)/g)).map(match => match[1]).filter(id => !ids.has(id))));
  }));
  expect(missing).toEqual([]);
});

test('compact form uses native fields; value bars require no Markdown syntax', async ({ page }) => {
  const { submissions } = await richChat(page, 'Plan your study.', [
    { id: 'form', kind: 'form', question: 'Study preferences', fields: [{ id: 'topic', kind: 'short_text', label: 'Topic', required: true }, { id: 'minutes', kind: 'number', label: 'Minutes', minimum: 5, maximum: 60, required: true }, { id: 'depth', kind: 'select', label: 'Depth', required: true, options: [{ id: 'brief', label: 'Brief' }, { id: 'deep', label: 'Deep' }] }], values: {}, submitted_turn_id: null },
    { id: 'bars', kind: 'value_bars', question: 'Relative difficulty', bars: [{ label: 'Concept A', value: 3, max: 5, unit: 'points', note: 'Illustrative rating' }, { label: 'Concept B', value: 4, max: 5, unit: 'points' }] },
  ]);
  await page.goto('/chat/polish-chat');
  const card = page.getByRole('region', { name: 'Interactive form' });
  await card.getByLabel('Topic', { exact: true }).fill('Indexes');
  await card.getByLabel('Minutes', { exact: true }).fill('2');
  await chooseOption(card.getByRole('combobox', { name: 'Depth' }), 'deep');
  await expect(card.getByRole('button', { name: 'Submit answer' })).toBeDisabled();
  await card.getByLabel('Minutes', { exact: true }).fill('20');
  await card.getByRole('button', { name: 'Submit answer' }).click();
  await expect(card.getByText('Answer submitted.')).toBeVisible();
  expect(submissions[0].interaction_response).toMatchObject({ values: { topic: 'Indexes', minutes: '20', depth: 'deep' } });
  await expect(page.getByRole('meter', { name: 'Concept A' })).toHaveAttribute('aria-valuenow', '3');
  await expect(page.getByText('3 / 5 points · 60%')).toBeVisible();
  await page.reload(); await expect(card.getByLabel('Topic', { exact: true })).toHaveValue('Indexes');
});

test('rich Markdown preserves ordinary percentages and clipboard text', async ({ page, context }, info) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await richChat(page, ':color[Success]{tone="success"} and :color[Needs review]{hex="#F54927"}. Ordinary 65% remains text.\n\n::bar{label="Estimated difficulty" value="3" max="5" unit="points"}\n\n:::details{title="Show a hint"}\nTry a small example.\n:::\n\n:::callout{title="Key idea" tone="info"}\nConnect the steps.\n:::\n\n`::bar{value="3"}` and :color[Literal]{hex="bad"}');
  await page.goto('/chat/polish-chat');
  const reply = page.getByRole('article', { name: 'Mentra response' }).last();
  await expect(reply.locator('.rich-color')).toHaveCount(3);
  await expect(reply.getByRole('meter')).toHaveCount(1);
  await expect(reply.getByText('Ordinary 65% remains text.', { exact: false })).toBeVisible();
  await reply.getByText('Show a hint', { exact: true }).click();
  await expect(reply.getByText('Try a small example.')).toBeVisible();
  await expect(reply.getByText(':color[Literal]{hex="bad"}', { exact: false })).toBeVisible();
  await reply.getByRole('button', { name: 'Copy response', exact: true }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain('Success and Needs review'); expect(copied).toContain('Estimated difficulty: 3 / 5 points · 60%'); expect(copied).toContain('::bar{value="3"}'); expect(copied).not.toContain('tone="success"');
  await page.screenshot({ path: info.outputPath('rich-markdown.png'), fullPage: true });
});

test('standalone disclosures and Markdown boundaries keep the optimized path correct', async ({ page }) => {
  await richChat(page, ':::details{title="Show explanation"}\nA helpful example.\n:::\n\n:::callout{title="Key idea"}\nKeep the scale consistent.\n:::\n\n1. First item\n\nA separate paragraph.\n\n    literal code\n\nFish &amp; chips');
  await page.goto('/chat/polish-chat');
  await page.getByText('Show explanation', { exact: true }).click();
  await expect(page.getByText('A helpful example.', { exact: true })).toBeVisible();
  await expect(page.locator('.rich-callout')).toContainText('Keep the scale consistent.');
  await expect(page.locator('.markdown-content ol')).toContainText('First item');
  await expect(page.locator('.markdown-content code')).toContainText('literal code');
  await expect(page.getByText('Fish & chips', { exact: true })).toBeVisible();
});

test('inline Lucide names render safely, keep text and copy without presentation tokens', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await richChat(page, ':icon[BookOpen] Reading and :icon[book-open] notes.\n\n:icon[Anvil] Practice. :icon[NotARealLucideIcon] Unknown. :icon[../../bad] Invalid.\n\nOrdinary BookOpen stays text. `:icon[BookOpen]` stays code.');
  await page.goto('/chat/polish-chat');
  const reply = page.getByRole('article', { name: 'Mentra response' }).last();
  await expect(reply.locator('.rich-icon svg')).toHaveCount(3);
  await expect(reply.locator('.rich-icon-placeholder')).toHaveCount(2);
  await expect(reply.locator('.rich-icon')).toHaveCount(5);
  for (const icon of await reply.locator('.rich-icon').all()) {
    await expect(icon).toHaveAttribute('aria-hidden', 'true');
    await expect(icon).toBeVisible();
    await expect(icon).toHaveText('');
  }
  await expect(reply).not.toContainText('NotARealLucideIcon');
  await expect(reply.locator('code')).toHaveText(':icon[BookOpen]');
  await reply.getByRole('button', { name: 'Copy response', exact: true }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain('Reading and');
  expect(copied).toContain('Ordinary BookOpen stays text.');
  expect(copied).toContain(':icon[BookOpen] stays code.');
  expect(copied).not.toContain('NotARealLucideIcon');
});

for (const chunk of ['lucideIconCatalog', 'anvil']) test(`unavailable ${chunk} leaves a placeholder and usable chat`, async ({ page }) => {
  await richChat(page, ':icon[Anvil] Practice stays readable.');
  let blocked = 0;
  await page.route(`**/${chunk}-*.js`, route => { blocked++; return route.abort(); });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/chat/polish-chat');
  await expect.poll(() => blocked).toBeGreaterThan(0);
  await expect(page.locator('.rich-icon-placeholder')).toBeVisible();
  await expect(page.getByText('Practice stays readable.', { exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeEditable();
  expect(errors).toEqual([]);
});

test('icons load only when requested and repeated names reuse the same module', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => requests.push(request.url()));
  await richChat(page, 'Ordinary response without icons.');
  await page.goto('/chat/polish-chat');
  await expect(page.getByText('Ordinary response without icons.', { exact: true })).toBeVisible();
  expect(requests.filter(url => /lucideIconCatalog|\/anvil-|\/a-arrow-down-/.test(url))).toEqual([]);
  await richChat(page, Array.from({ length: 40 }, () => ':icon[Anvil]').join(' '));
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.rich-icon svg')).toHaveCount(32);
  await expect(page.locator('.rich-icon-placeholder')).toHaveCount(8);
  expect(requests.filter(url => /lucideIconCatalog-/.test(url))).toHaveLength(1);
  expect(requests.filter(url => /\/anvil-/.test(url))).toHaveLength(1);
  expect(requests.filter(url => /\/a-arrow-down-/.test(url))).toHaveLength(0);
});

const diagrams: Record<string, string> = {
  flowchart: 'flowchart LR\n accTitle: Learning flow\n accDescr: Practice follows learning.\n A[Learn] --> B[Practice]',
  sequence: 'sequenceDiagram\n Student->>Mentra: Explain\n Mentra-->>Student: Example',
  state: 'stateDiagram-v2\n [*] --> Learning\n Learning --> Practice',
  class: 'classDiagram\n class Concept\n class Example\n Concept --> Example',
  er: 'erDiagram\n CONCEPT ||--o{ EXAMPLE : has',
  mindmap: 'mindmap\n root((Learning))\n  Practice\n  Examples',
  timeline: 'timeline\n title Learning\n First : Read\n Next : Practice',
  gantt: 'gantt\n title Study\n dateFormat YYYY-MM-DD\n Read :2026-10-27, 1d',
};
for (const [kind, code] of Object.entries(diagrams)) test(`Mermaid ${kind} renders and exposes source`, async ({ page }, info) => {
  await richChat(page, `A visual explanation.\n\n\`\`\`mermaid\n${code}\n\`\`\``);
  await page.goto('/chat/polish-chat');
  const figure = page.locator('.mermaid-figure');
  await expect(figure.locator('svg')).toBeVisible({ timeout: 20000 });
  // An SVG shell can render successfully even when sanitization removed every label.
  const labels = figure.locator('svg text').filter({ hasText: /\S/ });
  await expect(labels.first()).toBeVisible();
  await expect.poll(() => labels.allTextContents()).not.toEqual([]);
  if (kind === 'flowchart') {
    await expect(labels).toContainText(['Learn', 'Practice']);
  }
  await figure.getByRole('button', { name: 'Expand', exact: true }).click();
  const viewer = page.getByRole('dialog', { name: 'Expanded diagram' });
  await expect(viewer.locator('svg')).toBeVisible();
  const bounds = await viewer.boundingBox();
  const viewport = page.viewportSize()!;
  expect(bounds?.width).toBeGreaterThanOrEqual(viewport.width - 1);
  expect(bounds?.height).toBeGreaterThanOrEqual(viewport.height - 1);
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await figure.getByRole('button', { name: 'View source', exact: true }).click();
  await expect(figure.locator('code')).toContainText(code);
  if (kind === 'flowchart') await page.screenshot({ path: info.outputPath('mermaid-source.png') });
});

test('mobile dark fullscreen keeps multiline labels and restores focus on Escape', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark' });
  await richChat(page, '```mermaid\nflowchart TD\n A[Application starts] --> B[Create component]\n B --> C[Render template]\n C --> D{Data changed?}\n D -->|Yes| C\n D -->|No| E[View ready]\n```');
  await page.goto('/chat/polish-chat');
  const figure = page.locator('.mermaid-figure');
  await expect(figure.locator('svg text').filter({ hasText: 'Application starts' })).toBeVisible();
  await expect(figure.locator('foreignObject')).toHaveCount(0);
  const expand = figure.getByRole('button', { name: 'Expand', exact: true });
  await expand.click();
  const viewer = page.getByRole('dialog', { name: 'Expanded diagram' });
  await expect(viewer.locator('svg text').filter({ hasText: 'Render template' })).toBeVisible();
  expect(await viewer.boundingBox()).toMatchObject({ x: 0, y: 0, width: 390, height: 844 });
  await expect(viewer.getByRole('button', { name: 'Close', exact: true })).toBeInViewport();
  await page.screenshot({ path: info.outputPath('diagram-fullscreen-mobile.png'), animations: 'disabled' });
  await page.keyboard.press('Escape');
  await expect(viewer).toHaveCount(0);
  await expect(expand).toBeFocused();
});

test('invalid/unsafe Mermaid stays local, source remains readable', async ({ page }) => {
  await richChat(page, 'Before.\n\n```mermaid\nflowchart LR; A --> B; click A "https://example.com"\n```\n\n```mermaid\nnot valid syntax!\n```\n\nAfter.');
  await page.goto('/chat/polish-chat');
  await expect(page.getByText('After.', { exact: true })).toBeVisible();
  await expect(page.locator('.mermaid-figure code')).toHaveCount(2);
  await expect(page.locator('.mermaid-svg svg')).toHaveCount(0);
});

test('chat font sizes persist with medium default and leave surrounding UI unchanged', async ({ page }, info) => {
  await richChat(page, 'Clear, comfortable chat text.');
  await page.goto('/chat/polish-chat');
  const prose = page.getByRole('article', { name: 'Mentra response' }).locator('.chat-prose');
  await expect(prose).toHaveCSS('font-size', '16px');
  await page.evaluate(() => document.fonts.ready);
  expect(await prose.evaluate(element => getComputedStyle(element).fontFamily)).toContain('Inter Variable');
  const nav = page.getByRole('link', { name: 'Library', exact: true });
  const original = await nav.evaluate(element => getComputedStyle(element).fontSize);
  await page.goto('/settings');
  const control = page.getByRole('combobox', { name: 'Chat font size' });
  await expect(control).toContainText('Medium');
  await chooseOption(control, 'large');
  await expect(page.getByLabel('Chat text preview')).toHaveCSS('font-size', '18px');
  await page.goto('/chat/polish-chat'); await expect(prose).toHaveCSS('font-size', '18px');
  await expect(nav).toHaveCSS('font-size', original);
  await page.reload(); await expect(prose).toHaveCSS('font-size', '18px');
  await page.screenshot({ path: info.outputPath('chat-font-large.png') });
});

test('theme changes keep diagrams unique and color readable; malformed blocks stay literal', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const code = 'flowchart LR\n accTitle: Learning\n A[Learn] --> B[Practice]';
  await richChat(page, `:color[Important]{hex="#ffffff"}\n\n\`\`\`mermaid\n${code}\n\`\`\`\n\n\`\`\`mermaid\n${code}\n\`\`\`\n\n::bar{label="Bad" value="8" max="5"}\n\n:color[Literal]{hex="bad"}`);
  await page.goto('/chat/polish-chat');
  await expect(page.locator('.mermaid-svg > svg')).toHaveCount(2);
  const distinctIds = () => page.locator('.mermaid-svg [id]').evaluateAll(nodes => { const ids = nodes.map(node => node.id); return ids.length === new Set(ids).size; });
  expect(await distinctIds()).toBeTruthy();
  const firstId = await page.locator('.mermaid-svg > svg').first().getAttribute('id');
  await page.evaluate(() => { localStorage.setItem('mentra-theme', 'dark'); window.dispatchEvent(new StorageEvent('storage', { key: 'mentra-theme', newValue: 'dark', storageArea: localStorage })); });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect.poll(() => page.locator('.mermaid-svg > svg').first().getAttribute('id')).not.toBe(firstId);
  expect(await distinctIds()).toBeTruthy();
  await expect(page.getByRole('meter')).toHaveCount(0);
  const reply = page.getByRole('article', { name: 'Mentra response' }).last();
  await reply.getByRole('button', { name: 'Copy response', exact: true }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain('::bar{label="Bad" value="8" max="5"}');
  expect(copied).toContain(':color[Literal]{hex="bad"}');
});

test('chat font size synchronizes across tabs and handles small mobile text', async ({ page, context }) => {
  await workspace(page);
  await page.goto('/settings');
  const control = page.getByRole('combobox', { name: 'Chat font size' });
  await chooseOption(control, 'small');
  await expect(page.getByLabel('Chat text preview')).toHaveCSS('font-size', '15px');
  await page.setViewportSize({ width: 375, height: 812 });
  const other = await context.newPage(); await workspace(other); await other.goto('/chat/polish-chat');
  await expect(other.getByRole('article', { name: 'Mentra response' }).last().locator('.chat-prose')).toHaveCSS('font-size', '15px');
  await chooseOption(control, 'large');
  await expect(other.getByRole('article', { name: 'Mentra response' }).last().locator('.chat-prose')).toHaveCSS('font-size', '18px');
  await page.goto('/chat/polish-chat');
  await page.evaluate(() => { localStorage.setItem('mentra-chat-font-size', 'small'); window.dispatchEvent(new StorageEvent('storage', { key: 'mentra-chat-font-size', newValue: 'small' })); });
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toHaveCSS('font-size', '16px');
  await other.close();
});

test('chat appearance still works when local storage is blocked', async ({ page }) => {
  await page.addInitScript(() => { Storage.prototype.getItem = () => { throw new DOMException('Blocked'); }; Storage.prototype.setItem = () => { throw new DOMException('Blocked'); }; });
  await workspace(page); await page.goto('/settings');
  const control = page.getByRole('combobox', { name: 'Chat font size' });
  await expect(control).toContainText('Medium');
  await chooseOption(control, 'large');
  await expect(page.getByLabel('Chat text preview')).toHaveCSS('font-size', '18px');
  await page.getByRole('region', { name: 'Conversation history' }).locator('a[href="/chat/polish-chat"]').click();
  await expect(page.getByRole('article', { name: 'Mentra response' }).last().locator('.chat-prose')).toHaveCSS('font-size', '18px');
});
