import { test, expect, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';

async function openChat(page: Page) {
  await workspace(page);
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('log')).toBeVisible();
  await expect.poll(() => page.getByRole('log').evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(3);
}

for (const width of [390, 1280]) test(`jump to bottom appears only well above the latest messages at ${width}`, async ({page}, info) => {
  await page.setViewportSize({width, height:844});
  await page.emulateMedia({reducedMotion:width===390 ? 'reduce' : 'no-preference'});
  await openChat(page);
  const log = page.getByRole('log');
  const jump = page.getByRole('button', {name:'Scroll to bottom', exact:true});
  await expect(jump).toHaveCount(0);
  await log.hover();
  const initialTop = await log.evaluate(el => el.scrollTop);
  await page.mouse.wheel(0, -160);
  await expect.poll(() => log.evaluate(el => el.scrollTop)).toBeLessThan(initialTop - 100);
  await expect(jump).toHaveCount(0);
  await page.mouse.wheel(0, -900);
  await expect(jump).toBeVisible();
  await page.screenshot({path:info.outputPath('chat-jump-button.png')});
  await jump.click();
  await expect.poll(() => log.evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(3);
  await expect(jump).toHaveCount(0);
  expect(await page.evaluate(() => scrollY)).toBe(0);
  await log.hover(); await page.mouse.wheel(0, -1000);
  await expect(jump).toBeVisible();
  if (width===390) await page.getByRole('button',{name:'Open navigation menu',exact:true}).click();
  await page.getByRole('button', {name:'Start a new chat', exact:true}).click();
  await expect(jump).toHaveCount(0);
});

async function dragSidebar(page: Page, width: number) {
  const handle = page.getByRole('separator', {name:'Resize sidebar'});
  const bounds = (await handle.boundingBox())!;
  const sidebar = (await page.getByLabel('Main navigation', {exact:true}).boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width / 2, 300);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width / 2 + width - sidebar.width, 300, {steps:8});
  await page.mouse.up();
}

test('sidebar resizes, snaps below its expanded minimum and restores by dragging', async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await openChat(page);
  const sidebar = page.getByLabel('Main navigation', {exact:true});
  const handle = page.getByRole('separator', {name:'Resize sidebar'});
  await dragSidebar(page, 344);
  await expect(handle).toHaveAttribute('aria-valuenow','344');
  await expect.poll(() => sidebar.evaluate(el => el.getBoundingClientRect().width)).toBe(344);
  await dragSidebar(page, 200);
  await expect(handle).toHaveAttribute('aria-valuetext','Collapsed');
  await expect(page.getByRole('button',{name:'Expand sidebar',exact:true})).toBeVisible();
  await expect.poll(() => sidebar.evaluate(el => el.getBoundingClientRect().width)).toBe(56);
  await dragSidebar(page, 252);
  await expect(handle).toHaveAttribute('aria-valuenow','252');
  await expect(page.getByRole('button',{name:'Collapse sidebar',exact:true})).toBeVisible();
  await expect.poll(() => sidebar.evaluate(el => el.getBoundingClientRect().width)).toBe(252);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('sidebar keyboard controls and saved width preserve mobile navigation', async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await openChat(page);
  let handle = page.getByRole('separator',{name:'Resize sidebar'});
  await handle.focus(); await page.keyboard.press('End');
  await expect(handle).toHaveAttribute('aria-valuenow','400');
  await page.keyboard.press('Home');
  await expect(handle).toHaveAttribute('aria-valuenow','56');
  await page.reload();
  handle = page.getByRole('separator',{name:'Resize sidebar'});
  await expect(handle).toHaveAttribute('aria-valuenow','56');
  await handle.focus(); await page.keyboard.press('ArrowRight');
  await expect(handle).toHaveAttribute('aria-valuenow','400');
  await page.keyboard.press('ArrowLeft');
  await expect(handle).toHaveAttribute('aria-valuenow','384');
  await page.reload();
  await expect(handle).toHaveAttribute('aria-valuenow','384');
  await page.setViewportSize({width:390,height:844});
  await expect(handle).toBeHidden();
  await page.getByRole('button',{name:'Open navigation menu',exact:true}).click();
  const navigation = page.getByRole('dialog',{name:'Main navigation'});
  await expect(navigation).toBeVisible();
  await expect.poll(() => navigation.evaluate(el => el.getBoundingClientRect().width)).toBe(272);
  await navigation.getByRole('button',{name:'Close navigation menu',exact:true}).click();
  await expect(navigation).toHaveCount(0);
  await page.setViewportSize({width:1280,height:900});
  await expect(handle).toHaveAttribute('aria-valuenow','384');
});
