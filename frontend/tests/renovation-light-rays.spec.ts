import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

for (const theme of ['dark', 'light']) test(`empty chat light rays stay behind controls in ${theme}`, async ({page}, info) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.setViewportSize({width:1440,height:900});
  await page.addInitScript(value => localStorage.setItem('mentra-theme', value), theme);
  await workspace(page);
  await page.goto('/');
  const rays = page.locator('.light-rays');
  await expect(rays).toHaveCount(1);
  await expect(rays).toHaveAttribute('aria-hidden','true');
  await expect.poll(() => page.locator('.light-rays canvas').evaluate((canvas: HTMLCanvasElement) => canvas.width > 1 && canvas.height > 1)).toBe(true);
  await page.getByRole('button',{name:'Explain a concept',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Ask Mentra anything'})).toHaveValue('Help me understand a concept: ');
  await page.mouse.move(1000,300);
  await page.waitForTimeout(1900);
  await page.screenshot({path:info.outputPath(`light-rays-${theme}.png`)});
  await page.getByRole('textbox',{name:'Ask Mentra anything'}).press('Enter');
  await expect(page.getByRole('log')).toBeVisible();
  await expect(rays).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('reduced motion renders once and still follows theme changes', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.addInitScript(() => {
    const original = WebGL2RenderingContext.prototype.drawArrays;
    Object.assign(window, {raysDraws:0});
    WebGL2RenderingContext.prototype.drawArrays = function(...args) {
      const state = window as typeof window & {raysDraws:number};
      state.raysDraws++;
      return original.apply(this,args);
    };
  });
  await workspace(page);
  await page.goto('/');
  const draws = () => page.evaluate(() => (window as typeof window & {raysDraws:number}).raysDraws);
  await expect.poll(draws).toBeGreaterThan(0);
  await page.waitForTimeout(300);
  const count = await draws();
  await page.mouse.move(900,200);
  await page.waitForTimeout(300);
  expect(await draws()).toBe(count);
  await page.evaluate(() => { document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; });
  await expect.poll(draws).toBeGreaterThan(count);
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('log')).toBeVisible();
  await expect(page.locator('.light-rays')).toHaveCount(0);
  const stopped = await draws();
  await page.waitForTimeout(200);
  expect(await draws()).toBe(stopped);
  await page.getByRole('button',{name:'Start a new chat',exact:true}).click();
  await expect(page.locator('.light-rays')).toHaveCount(1);
  await expect.poll(draws).toBeGreaterThan(stopped);
});

test('chat remains usable without WebGL', async ({page}) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type: string, ...args: unknown[]) {
      if (type === 'webgl2') return null;
      return Reflect.apply(original, this, [type,...args]);
    } as typeof original;
  });
  await page.setViewportSize({width:390,height:844});
  await workspace(page);
  await page.goto('/');
  await page.getByRole('button',{name:'Quiz me',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Ask Mentra anything'})).toHaveValue('Quiz me on ');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
