import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { richChat } from './renovation-rich-fixtures';

const diagram = `flowchart TD
 subgraph Campaign[Campaign and battle]
 A[Timur occupies the water sources] --> B[Ottoman army arrives exhausted]
 B --> C{Allies remain loyal?}
 C -->|No| D[The Ottoman line collapses]
 end`;

for (const theme of ['light', 'dark']) for (const width of [390, 1280]) test(`Mentra diagram styling and standalone export in ${theme} at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 1000 });
  await page.addInitScript(theme => localStorage.setItem('mentra-theme', theme), theme);
  await richChat(page, '```mermaid\n' + diagram + '\n```');
  await page.goto('/chat/polish-chat');
  const figure = page.locator('.mermaid-figure');
  await expect(figure.locator('.node text').first()).toBeVisible({ timeout: 20000 });
  const node = figure.locator('.node rect').first();
  const colors = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    const rgb = (name: string) => `rgb(${style.getPropertyValue(`--${name}`).trim().split(/\s+/).join(', ')})`;
    return { card: rgb('card'), border: rgb('border-strong'), text: rgb('foreground'), surface: rgb('surface') };
  });
  await expect(node).toHaveCSS('fill', colors.card);
  await expect(node).toHaveCSS('stroke', colors.border);
  await expect(node).toHaveCSS('rx', '10px');
  await expect(node).toHaveCSS('filter', 'none');
  await expect(figure.locator('.cluster rect').first()).toHaveCSS('fill', colors.surface);
  await expect(figure.locator('.node text').first()).toHaveCSS('fill', colors.text);
  expect(await figure.locator('.node text').first().evaluate(node => getComputedStyle(node).fontFamily)).toContain('Inter Variable');
  await figure.screenshot({ path: info.outputPath(`diagram-${theme}-${width}.png`) });
  await figure.getByRole('button', { name: 'Expand', exact: true }).click();
  const modal = page.getByRole('dialog', { name: 'Expanded diagram' });
  await expect(modal.locator('.node rect').first()).toHaveCSS('rx', '10px');
  await expect(modal.locator('.node rect').first()).toHaveCSS('fill', colors.card);
  await page.keyboard.press('Escape');
  const [download] = await Promise.all([page.waitForEvent('download'), figure.getByRole('button', { name: 'Download SVG', exact: true }).click()]);
  const svg = await readFile((await download.path())!, 'utf8');
  expect(svg).toContain('Inter Variable');
  expect(svg).toContain('rx:10px');
  expect(svg).not.toContain('foreignObject');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
