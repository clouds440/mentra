import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

async function register(page: Page) {
  await page.goto('/register');
  await page.getByLabel('Username', { exact: true }).fill(`code_${randomUUID().slice(0, 8)}`);
  await page.getByLabel('Password', { exact: true }).fill('a unique code display passphrase');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await finishOnboardingWithoutAssessment(page);
  await expect(page).toHaveURL(/\/$/);
}
const userCode = 'type GreetingProps = { name: string };\n\nexport function Greeting({ name }: GreetingProps) {\n  return <h1>Hello, {name}!</h1>;\n}';
const assistant = '# A small component, explained\n\nYour `Greeting` component is already doing the right thing. Here is the same idea in Python:\n\n```python\nfrom functools import wraps\n\ndef trace(fn):\n    @wraps(fn)\n    def wrapper(*args, **kwargs):\n        print(f"Calling {fn.__name__}")\n        return fn(*args, **kwargs)\n    return wrapper\n```\n\n| Pattern | Purpose |\n| --- | --- |\n| Props | Typed inputs |\n| Wrapper | Reusable behavior |\n\n- [x] Keep source formatting\n- [x] Make examples easy to copy';

for (const theme of ['light', 'dark'] as const) {
  test(`user and assistant Markdown/code are highlighted in ${theme}`, async ({ page, context }, testInfo) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1440, height: 1100 });
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await register(page);
    await page.route('**/api/v1/conversations/turns', async route => { const response = await route.fetch(); const body = await response.json(); body.items.at(-1).content = assistant; await route.fulfill({ json: body }); });
    await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Can you explain this component?\n\n```tsx\n' + userCode + '\n```');
    await page.getByRole('button', { name: 'Send message' }).click();
    const user = page.getByRole('article', { name: 'Your message' });
    const reply = page.getByRole('article', { name: 'Mentra response' });
    await expect(user.locator('.token.keyword').first()).toBeVisible();
    await expect(reply.locator('.token.keyword').first()).toBeVisible();
    await expect(user.locator('.code-pre code')).toHaveText(userCode);
    await expect(reply.getByRole('heading', { name: 'A small component, explained' })).toBeVisible();
    await expect(reply.getByRole('table')).toBeVisible();
    await user.getByRole('button', { name: 'Copy code', exact: true }).click();
    await expect(user.getByRole('button', { name: 'Code copied', exact: true })).toBeVisible();
    expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n')).toBe(userCode);
    await user.getByRole('button', { name: 'Wrap code lines' }).click();
    await expect(user.locator('.code-scroll')).toHaveClass(/code-wrapped/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`code-chat-${theme}.png`), fullPage: true, animations: 'disabled' });
  });
}

test('mobile code keeps long lines contained and unknown grammars remain safe', async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await register(page);
  await page.setViewportSize({ width: 320, height: 720 });
  const code = 'const example = "' + 'long source line '.repeat(20) + '";\nconst unsafe = "<img src=x onerror=alert(1)>";';
  await page.route('**/api/v1/conversations/turns', async route => { const response = await route.fetch(); const body = await response.json(); body.items.at(-1).content = '```javascript\n' + code + '\n```\n\n```future-language\n<script>window.unsafeExecuted = true</script>\n```'; await route.fulfill({ json: body }); });
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).fill('Show me a code example.');
  await page.getByRole('button', { name: 'Send message' }).click();
  const reply = page.getByRole('article', { name: 'Mentra response' });
  await expect(reply.locator('.token.keyword').first()).toBeVisible();
  const block = reply.locator('.code-block').first();
  await expect(block.locator('.code-pre code')).toHaveText(code);
  expect(await block.locator('.code-scroll').evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(reply.locator('.code-block img, .code-block script')).toHaveCount(0);
  await expect(reply.locator('[data-language="plain"] code')).toContainText('<script>');
  await block.getByRole('button', { name: 'Wrap code lines' }).click();
  expect(await block.locator('.code-scroll').evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('code-chat-mobile-dark.png'), fullPage: true, animations: 'disabled' });
});

test('Library code and HTML script/style metadata reach the polished source reader', async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await register(page);
  await page.goto('/library');
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'Greeting.tsx', mimeType: 'text/plain', buffer: Buffer.from(userCode) });
  await page.getByLabel('Material title', { exact: true }).fill('Greeting component');
  await page.getByLabel('New context name', { exact: true }).fill('React');
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Study in chat' })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('link', { name: 'Greeting component', exact: true }).click();
  await page.getByRole('button', { name: 'Open source version' }).click();
  const dialog = page.getByRole('dialog', { name: 'Source: Greeting component' });
  await expect(dialog.locator('.token.keyword').first()).toBeVisible();
  await expect(dialog.locator('.code-pre code')).toHaveText(userCode);
  let originals = 0;
  page.on('request', request => { if (/\/versions\/[^/]+\/source\?/.test(request.url())) originals++; });
  await dialog.getByRole('button', { name: 'Original file', exact: true }).click();
  await expect(dialog.locator('.code-filename')).toHaveText('Greeting.tsx');
  await expect(dialog.locator('.code-pre code')).toHaveText(userCode);
  const download = page.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Download original' }).click();
  expect((await download).suggestedFilename()).toBe('Greeting.tsx');
  expect(originals).toBe(1);
  await page.screenshot({ path: testInfo.outputPath('code-source-dark.png'), fullPage: true, animations: 'disabled' });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.screenshot({ path: testInfo.outputPath('code-source-light.png'), fullPage: true, animations: 'disabled' });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 320, height: 720 });
  expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('code-source-mobile-dark.png'), fullPage: true, animations: 'disabled' });
  await dialog.getByRole('button', { name: 'Close source' }).click();
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'inline.html', mimeType: 'text/html', buffer: Buffer.from('<h1>A page</h1><script>const greet = "hello";</script><style>.greet { color: blue; }</style>') });
  await page.getByRole('button', { name: 'Submit replacement' }).click();
  await expect(page.getByText(/inline.html.*Latest upload/)).toBeVisible();
  await expect(page.getByText('Ready to study', { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Open source version' }).first().click();
  await expect(dialog.locator('[data-language="javascript"] .token.keyword')).toBeVisible();
  await expect(dialog.locator('[data-language="css"] .token.property')).toBeVisible();
});

test('Markdown uploads render rich content and adjacent source chunks stay continuous', async ({ page }) => {
  await register(page);
  await page.goto('/library');
  const markdown = '# JavaScript notes\n\nHere is a reusable pattern with `const`.\n\n```js\nconst answer = 42;\n```\n\n| Kind | Example |\n| --- | --- |\n| Value | 42 |';
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'notes.md', mimeType: 'text/markdown', buffer: Buffer.from(markdown) });
  await page.getByLabel('Material title', { exact: true }).fill('Code notes');
  await page.getByLabel('New context name', { exact: true }).fill('Code');
  await page.getByRole('button', { name: 'Upload material', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Study in chat' })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('link', { name: 'Code notes', exact: true }).click();
  await page.getByRole('button', { name: 'Open source version' }).click();
  const dialog = page.getByRole('dialog', { name: 'Source: Code notes' });
  await expect(dialog.getByRole('heading', { name: 'JavaScript notes' })).toBeVisible();
  await expect(dialog.getByRole('table')).toBeVisible();
  await expect(dialog.locator('.token.keyword')).toBeVisible();
  await dialog.getByRole('button', { name: 'Close source' }).click();
  const code = Array.from({ length: 140 }, (_, index) => `const item${index}: number = ${index};`).join('\n');
  await page.getByLabel('File', { exact: true }).setInputFiles({ name: 'long.ts', mimeType: 'text/plain', buffer: Buffer.from(code) });
  await page.getByRole('button', { name: 'Submit replacement' }).click();
  await expect(page.getByText(/long.ts.*Latest upload/)).toBeVisible();
  await expect(page.getByText('Ready to study', { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Open source version' }).first().click();
  await expect(dialog.locator('.code-pre code')).toHaveText(code);
  await expect(dialog.locator('header')).toContainText(/[2-9] passages/);
  await expect(dialog.locator('.source-passage')).toHaveCount(1);
});
