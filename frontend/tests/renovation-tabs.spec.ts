import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

for (const theme of ['light','dark']) {
  test(`tabs scroll on one line with boundary-aware rounded arrows ${theme}`, async ({page}, info) => {
    await workspace(page, false, true);
    await page.addInitScript(value => localStorage.setItem('mentra-theme', value), theme);
    await page.setViewportSize({width:320,height:850});
    await page.goto('/assessments');
    const tabs=page.getByRole('tablist',{name:'Assessment sections'});
    const left=page.getByRole('button',{name:'Scroll assessment sections left'});
    const right=page.getByRole('button',{name:'Scroll assessment sections right'});
    await expect(right).toBeVisible(); await expect(left).toHaveCount(0);
    const tops=await tabs.getByRole('tab').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().top));
    expect(new Set(tops).size).toBe(1);
    expect(await right.evaluate(node => getComputedStyle(node).borderRadius)).toBe('9999px');
    await right.click();
    await expect(right).toHaveCount(0); await expect(left).toBeVisible();
    await left.click();
    await expect(left).toHaveCount(0); await expect(right).toBeVisible();
    await tabs.getByRole('tab',{name:'Assessments',exact:true}).focus();
    await page.keyboard.press('End');
    await expect(tabs.getByRole('tab',{name:'Create new'})).toBeFocused();
    await expect(right).toHaveCount(0);
    await page.keyboard.press('Home');
    await expect(left).toHaveCount(0);
    await page.screenshot({path:info.outputPath('tabs-mobile.png')});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.setViewportSize({width:1440,height:900});
    await expect(left).toHaveCount(0); await expect(right).toHaveCount(0);
    await page.getByRole('tab',{name:'Practice my mistakes'}).click();
    await page.setViewportSize({width:320,height:850});
    const selected=tabs.getByRole('tab',{name:'Practice my mistakes'});
    await expect(selected).toBeInViewport();
  });
}
