import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

test('desktop chat actions support keyboard menus and inline rename', async ({page}) => {
  await workspace(page,false,true);
  await page.setViewportSize({width:1280,height:850});
  await page.goto('/chat/polish-chat');
  const trigger=page.getByRole('region',{name:'Conversation history'}).getByRole('button',{name:/Actions for/});
  await trigger.focus(); await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('menuitem',{name:'Rename',exact:true})).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('menuitem',{name:'Delete',exact:true})).toBeFocused();
  await page.keyboard.press('Escape'); await expect(trigger).toBeFocused();
  await trigger.click(); await page.getByRole('menuitem',{name:'Rename',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Conversation title'})).toBeFocused();
});

test('touch long press opens menu, suppresses navigation and cancels on movement', async ({browser}) => {
  const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true});
  const page=await context.newPage();
  await workspace(page,false,true);
  await page.goto('/');
  await page.getByRole('button',{name:'Open navigation menu'}).click();
  const row=page.getByRole('region',{name:'Conversation history'}).getByRole('link').first();
  const pointer={pointerId:1,pointerType:'touch',isPrimary:true,button:0,clientX:90,clientY:220};
  await row.dispatchEvent('pointerdown',pointer);
  await row.dispatchEvent('pointermove',{...pointer,clientY:250});
  await page.waitForTimeout(600);
  await expect(page.getByRole('menu')).toHaveCount(0);
  await row.dispatchEvent('pointerup',pointer);
  await row.dispatchEvent('pointerdown',pointer);
  await expect(page.getByRole('menu')).toBeVisible();
  await row.dispatchEvent('pointerup',pointer);
  await row.dispatchEvent('click');
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('menuitem',{name:'Delete',exact:true})).toBeVisible();
  expect(await page.getByRole('menu').evaluate(node => node.getBoundingClientRect().right <= innerWidth)).toBe(true);
  await page.keyboard.press('Escape');
  await row.dispatchEvent('pointerdown',pointer); await row.dispatchEvent('pointerup',pointer); await row.click();
  await expect(page).toHaveURL(/\/chat\/polish-chat$/);
  await context.close();
});
