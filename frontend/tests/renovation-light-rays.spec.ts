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
  await page.mouse.move(1000,300);
  await page.waitForTimeout(1900);
  await page.screenshot({path:info.outputPath(`light-rays-${theme}.png`)});
  const request = page.waitForRequest(item => item.url().endsWith('/conversations/turns') && item.method() === 'POST');
  await page.getByRole('button',{name:'Explain a concept',exact:true}).click();
  expect((await request).postDataJSON().content).toBe('Help me understand a concept. Ask me which topic to explore.');
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
  const request = page.waitForRequest(item => item.url().endsWith('/conversations/turns') && item.method() === 'POST');
  await page.getByRole('button',{name:'Quiz me',exact:true}).click();
  expect((await request).postDataJSON().content).toBe('Give me a short quiz to practice what I am learning.');
  await expect(page.getByRole('log')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('sidebar toggles and composer typing do not rerender or recreate LightRays', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => {
    let previous = new Set<object>();
    const state = { renders: 0, programs: 0 };
    Object.assign(window, { raysHardening: state, __REACT_DEVTOOLS_GLOBAL_HOOK__: {
      supportsFiber: true, renderers: new Map(), inject: () => 1,
      onCommitFiberRoot: (_id: number, root: any) => {
        const next = new Set<object>();
        function visit(fiber: any) {
          while (fiber) {
            next.add(fiber);
            if (!previous.has(fiber) && (fiber.flags & 1) && (fiber.elementType?.displayName ?? fiber.type?.displayName ?? fiber.type?.name) === 'LightRays') state.renders++;
            visit(fiber.child); fiber = fiber.sibling;
          }
        }
        visit(root.current); previous = next;
      }, onCommitFiberUnmount: () => {},
    } });
    const create = WebGL2RenderingContext.prototype.createProgram;
    WebGL2RenderingContext.prototype.createProgram = function() { state.programs++; return create.call(this); };
  });
  await workspace(page); await page.goto('/');
  const canvas = page.locator('.light-rays canvas');
  await expect.poll(() => page.evaluate(() => (window as any).raysHardening.programs)).toBeGreaterThan(0);
  const before = await page.evaluate(() => ({ ...(window as any).raysHardening }));
  expect(before.renders).toBeGreaterThan(0);
  const original = await canvas.elementHandle();
  for (let index = 0; index < 3; index++) {
    await page.getByRole('button', { name: 'Collapse sidebar', exact: true }).click();
    await page.getByRole('button', { name: 'Expand sidebar', exact: true }).click();
  }
  await page.getByRole('textbox', { name: 'Ask Mentra anything' }).pressSequentially('Keep the light rays stable', { delay: 20 });
  expect(await original!.evaluate(element => element.isConnected)).toBe(true);
  expect(await page.evaluate(() => (window as any).raysHardening)).toEqual(before);
});

for (const reduced of [false, true]) test(`canvas resize and redraw stay in one frame with reduced motion ${reduced}`, async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: reduced ? 'reduce' : 'no-preference' });
  await page.addInitScript(() => {
    const state = { writes: 0, outsideFrame: 0, blankFrames: 0, draws: 0 };
    Object.assign(window, { raysResizeProfile: state });
    let inFrame = false; let pending = false;
    const request = window.requestAnimationFrame;
    window.requestAnimationFrame = callback => request.call(window, now => {
      inFrame = true;
      try { callback(now); } finally { if (pending) state.blankFrames++; inFrame = false; }
    });
    for (const key of ['width', 'height']) {
      const descriptor = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, key)!;
      Object.defineProperty(HTMLCanvasElement.prototype, key, { ...descriptor, set(value) {
        if (this.classList.contains('light-rays__canvas') && descriptor.get!.call(this) !== value) {
          state.writes++; pending = true; if (!inFrame) state.outsideFrame++;
        }
        descriptor.set!.call(this, value);
      } });
    }
    const draw = WebGL2RenderingContext.prototype.drawArrays;
    WebGL2RenderingContext.prototype.drawArrays = function(...args) {
      const result = draw.apply(this, args);
      if ((this.canvas as HTMLCanvasElement).classList.contains('light-rays__canvas')) { pending = false; state.draws++; }
      return result;
    };
  });
  await workspace(page); await page.goto('/');
  await expect.poll(() => page.evaluate(() => (window as any).raysResizeProfile.draws)).toBeGreaterThan(0);
  const initial = await page.evaluate(() => ({ ...(window as any).raysResizeProfile }));
  for (const width of [1300, 1500, 1360]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole('button', { name: 'Collapse sidebar', exact: true }).click();
    await page.getByRole('button', { name: 'Expand sidebar', exact: true }).click();
  }
  await expect.poll(() => page.evaluate(() => (window as any).raysResizeProfile.writes)).toBeGreaterThan(initial.writes);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const result = await page.evaluate(() => (window as any).raysResizeProfile);
  expect(result.outsideFrame).toBe(0);
  expect(result.blankFrames).toBe(0);
  expect(result.draws).toBeGreaterThan(initial.draws);
});
