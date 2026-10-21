import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';

for (const width of [320, 390, 1440]) test(`cached mistake pages, compact controls and practice modal at ${width}`, async ({page}, info) => {
  await page.setViewportSize({width, height:900});
  await page.addInitScript(() => localStorage.setItem('mentra-theme', 'dark'));
  await workspace(page);
  const reads: string[] = [];
  await page.route('**/api/v1/assessments/mistakes?**', route => {
    const params = new URL(route.request().url()).searchParams;
    reads.push(params.toString());
    expect(params.get('limit')).toBe('10'); expect(params.get('recent')).toBe('true');
    const offset = Number(params.get('offset'));
    const items = Array.from({length:Math.min(10, 23-offset)}, (_, i) => ({id:`row-${offset+i}`, assessment_id:'paper', assessment_title:'Mechanics practice', attempt_id:'attempt', prompt:`Recent question ${offset+i+1}` + ' Long explanatory text.'.repeat(40), context:'', topics:[], score:0, marks:2, feedback:'Try using consistent units.', answer:'4 N', occurrences:1, resolved:false, occurred_at:'2026-10-21T10:00:00Z', priority:'Incorrect answer'}));
    return route.fulfill({json:{items,total:23,active_count:23,next_offset:offset+10<23 ? offset+10 : null,assessments:[{id:'paper',title:'Mechanics practice'}],topics:[],contexts:[{id:'context-1',name:'Mechanics'}]}});
  });
  await page.goto('/assessments?tab=mistakes');
  await expect(page.getByRole('button',{name:'Review mistake',exact:true})).toHaveCount(10);
  await expect(page.getByRole('combobox',{name:'Mistake assessments'})).toHaveCount(0);
  const cards = page.locator('.workspace-compact-grid > li');
  const geometry = await cards.evaluateAll(items => items.slice(0,2).map(item => ({x:item.getBoundingClientRect().x,y:item.getBoundingClientRect().y,height:item.getBoundingClientRect().height,overflow:item.scrollWidth>item.clientWidth})));
  expect(geometry[0].y).toBe(geometry[1].y); expect(geometry[1].x).toBeGreaterThan(geometry[0].x);
  expect(geometry.every(item => item.height===224 && !item.overflow)).toBe(true);
  await page.screenshot({path:info.outputPath('mistake-grid.png'),animations:'disabled'});
  await cards.first().getByRole('button',{name:'Review mistake'}).click();
  await expect(page.getByRole('dialog',{name:'Review mistake'}).getByRole('group',{name:'Your answer'})).toBeVisible();
  await page.keyboard.press('Escape');
  const pagination = page.getByRole('navigation',{name:'Mistake history pages'});
  await expect(pagination.getByRole('button',{name:'Previous page'})).toBeDisabled();
  expect(await pagination.innerText()).not.toMatch(/Previous|Next/);
  const heights = await pagination.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getBoundingClientRect().height));
  expect(new Set(heights).size).toBe(1);
  if (width === 1440) expect(heights[0]).toBe(28);
  await pagination.getByRole('button',{name:'Page 2',exact:true}).click();
  await expect(page.getByText(/^Recent question 11/)).toBeVisible();
  await pagination.getByRole('button',{name:'Previous page'}).click();
  await expect(page.getByText(/^Recent question 1 Long/)).toBeVisible();
  expect(reads).toHaveLength(2);
  await page.getByRole('button',{name:'List view',exact:true}).click();
  await expect(page.getByRole('group',{name:'Your answer'}).first()).toBeVisible();
  expect(reads).toHaveLength(2);
  await expect(page.getByRole('combobox',{name:'Revision question count'})).toHaveCount(0);
  await page.getByRole('button',{name:'Practice my mistakes',exact:true}).click();
  const dialog = page.getByRole('dialog',{name:'Practice my mistakes'});
  await expect(dialog.getByRole('combobox',{name:'Revision question count'})).toBeVisible();
  await dialog.getByRole('combobox',{name:'Mistake learning contexts'}).click();
  await page.getByRole('option',{name:'Mechanics',exact:true}).click();
  await page.keyboard.press('Escape');
  await expect(page).toHaveURL(/mistake_context=context-1/);
  await expect.poll(() => reads.length).toBe(3);
  expect(reads[2]).toContain('context_id=context-1');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Practice my mistakes',exact:true})).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('mistake-list.png'),fullPage:true});
});

test('wide conversation grows while composer retains its original width', async ({page}, info) => {
  await page.setViewportSize({width:1920,height:1080});
  await workspace(page);
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('log')).toBeVisible();
  const width = await page.getByRole('log').locator(':scope > div').evaluate(el => el.getBoundingClientRect().width);
  const composerWidth = await page.locator('.chat-composer-region > div').last().evaluate(el => el.getBoundingClientRect().width);
  expect(width).toBe(960); expect(composerWidth).toBe(832);
  await page.screenshot({path:info.outputPath('wide-chat.png')});
});

test('Concepts shares compact pagination and retains working page navigation', async ({page}) => {
  await workspace(page, false, true);
  const result = (offset = 0) => ({items:[{concept_id:`concept-${offset}`,name:`Concept ${offset+1}`,knowledge_status:'developing',mastery:.5,estimate_confidence:.5,retention_confidence:.5}],total:23,total_concepts:23,limit:10,offset,generated_at:'2026-10-21T10:00:00Z'});
  await page.route('**/api/v1/learning/page**', route => route.fulfill({json:{overview:{learner:{concepts:[],context_ids:[]},recommendations:[],verification:[]},contexts:[],candidates:[],understanding:result()}}));
  await page.route('**/api/v1/learning/understanding?**', route => route.fulfill({json:result(Number(new URL(route.request().url()).searchParams.get('offset')))}));
  await page.goto('/progress');
  const pagination = page.getByRole('navigation',{name:'Understanding pages'});
  await expect(pagination).toBeVisible();
  expect(await pagination.innerText()).not.toMatch(/Previous|Next/);
  await pagination.getByRole('button',{name:'Next page'}).click();
  await expect(page.getByText('Concept 11',{exact:true})).toBeVisible();
  await expect(pagination.getByRole('button',{name:'Page 2',exact:true})).toHaveAttribute('aria-current','page');
  expect(await pagination.getByRole('button').evaluateAll(buttons => new Set(buttons.map(button => button.getBoundingClientRect().height)).size)).toBe(1);
});

for (const theme of ['light','dark']) test(`empty chat and account menu remain usable in ${theme}`, async ({page}, info) => {
  await page.setViewportSize({width:1440,height:900});
  await page.addInitScript(value => localStorage.setItem('mentra-theme', value), theme);
  await workspace(page);
  await page.goto('/');
  await page.getByRole('button',{name:'Explain a concept',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Ask Mentra anything'})).toHaveValue('Help me understand a concept: ');
  await page.getByRole('button',{name:'Account menu for learner'}).click();
  await expect(page.getByRole('link',{name:'Settings',exact:true})).toBeVisible();
  await page.screenshot({path:info.outputPath(`account-${theme}.png`), animations:'disabled'});
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Account menu for learner'})).toHaveAttribute('aria-expanded','false');
});
