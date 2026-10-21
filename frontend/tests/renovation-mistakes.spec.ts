import { test, expect, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';

const topic = {id:'topic-1', name:'Newton’s second law'};
const sources = [{id:'paper-1', title:'Forces and motion'}, {id:'paper-2', title:'Applied mechanics'}];
const mistakes = sources.map((source, i) => ({id:`mistake-${i}`, assessment_id:source.id, assessment_title:source.title,
  attempt_id:`attempt-${i}`, grade_revision:1, question_id:`question-${i}`, prompt:`Find the resultant force for experiment ${i+1}.`,
  context:'A cart moves along a horizontal track.', topics:[topic], score:i, marks:2, feedback:'Include the direction and use consistent units.',
  answer:i ? '["b","c"]' : '4 N to the left', answer_mode:i ? 'multiple_choice' : 'text', options:i ? [{id:'b',label:'Mass times acceleration'},{id:'c',label:'To the right'}] : [], occurrences:3-i, resolved:false, occurred_at:'2026-10-19T10:00:00Z', priority:i ? 'Partial answer' : 'Repeated mistake'}));

async function fixture(page: Page) {
  await workspace(page, false, true);
  await page.route('**/api/v1/assessments/mistakes?**', route => {
    const params = new URL(route.request().url()).searchParams;
    const ids = params.getAll('assessment_id');
    const items = mistakes.filter(item => !ids.length || ids.includes(item.assessment_id));
    return route.fulfill({json:{items,total:items.length,active_count:items.length,next_offset:null,assessments:sources,topics:[topic]}});
  });
}

for (const [width, theme] of [[320,'light'],[390,'dark'],[1440,'light']] as const) {
  test(`mistake workspace filters and source links ${width} ${theme}`, async ({page}, info) => {
    await page.setViewportSize({width,height:900});
    await page.addInitScript(value => localStorage.setItem('mentra-theme',value),theme);
    await fixture(page);
    await page.goto('/assessments?tab=mistakes&mistake_view=list');
    await expect(page.getByRole('group',{name:'Your answer'}).first()).toContainText('4 N to the left');
    await expect(page.getByRole('group',{name:'Your answer'}).last()).toContainText('Mass times acceleration');
    await expect(page.getByRole('tab',{name:'Practice my mistakes'})).toHaveAttribute('aria-selected','true');
    await expect(page.getByRole('link',{name:'Forces and motion'})).toHaveAttribute('href','/assessments?assessment=paper-1&attempt=attempt-0');
    await page.getByRole('button',{name:'Practice my mistakes',exact:true}).click();
    await page.getByRole('combobox',{name:'Mistake assessments',exact:true}).click();
    await page.getByRole('option',{name:'Forces and motion',exact:true}).click();
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Close practice options'}).click();
    await expect(page).toHaveURL(/mistake_assessment=paper-1/);
    await expect(page.getByText('1 to revisit · 0 corrected')).toBeVisible();
    await expect(page.getByRole('link',{name:'Applied mechanics',exact:true})).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Practice my mistakes',exact:true})).toBeEnabled();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:info.outputPath('mistakes.png'),fullPage:true});
    await page.reload();
    await expect(page.getByText('1 to revisit · 0 corrected')).toBeVisible();
  });
}

test('automatic practice retries the same operation and opens the tagged revision', async ({page}) => {
  await fixture(page);
  const bodies: Record<string,unknown>[] = [];
  const result = {id:'revision-1',context_id:'context-1',title:'Revision assessment',purpose:'practice',revision:1,
    created_at:'2026-10-19T10:00:00Z',questions:[],sources:[],tags:['revision assessment'],source_assessment_ids:['paper-1','paper-2'],
    practice_source:{assessment_id:'paper-1',attempt_id:'attempt-0',grade_revision:1,known_exposure:true,instructions:'',reference_questions:[]}};
  await page.route('**/api/v1/assessments/mistakes/practice', route => {
    bodies.push(route.request().postDataJSON());
    return bodies.length === 1 ? route.fulfill({status:503,json:{error:{code:'UNAVAILABLE',message:'Please retry.'}}})
      : route.fulfill({json:{id:'revision-job',state:'queued',title:'Revision assessment',completed_parts:0,total_parts:2,result:null,error:null,can_retry:false}});
  });
  await page.route('**/api/v1/assessments/generation-jobs/revision-job', route => route.fulfill({json:{id:'revision-job',state:'completed',title:'Revision assessment',completed_parts:2,total_parts:2,result,error:null,can_retry:false}}));
  await page.route('**/api/v1/assessments/page?**', route => route.fulfill({json:{items:[],next_offset:null,contexts:[],detail:new URL(route.request().url()).searchParams.get('assessment_id') === 'revision-1' ? result : null,attempts:[]}}));
  await page.route('**/api/v1/assessments/revision-1', route => route.fulfill({json:result}));
  await page.route('**/api/v1/assessments/revision-1/attempts', route => route.fulfill({json:[]}));
  await page.goto('/assessments?tab=mistakes&mistake_view=list');
  await page.getByRole('button',{name:'Practice my mistakes',exact:true}).click();
  await page.getByRole('button',{name:'Generate practice',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Mentra could not complete this request.');
  await page.getByRole('button',{name:'Generate practice',exact:true}).click();
  await expect(page).toHaveURL(/assessment=revision-1/);
  expect(bodies[0]).toEqual(bodies[1]);
  expect(bodies[0]).toMatchObject({assessment_ids:[],topic_ids:[],count:5});
  await expect(page.getByRole('link',{name:'Source assessment 1'})).toHaveAttribute('href','/assessments?assessment=paper-1');
  await expect(page.getByRole('link',{name:'Source assessment 2'})).toHaveAttribute('href','/assessments?assessment=paper-2');
});

test('topic filters reach the server and an empty history cannot generate', async ({page}) => {
  await fixture(page);
  await page.goto('/assessments?tab=mistakes&mistake_view=list');
  await page.getByRole('button',{name:'Practice my mistakes',exact:true}).click();
  await page.getByRole('combobox',{name:'Mistake topics',exact:true}).click();
  const requested = page.waitForRequest(request => request.url().includes('/mistakes?') && request.url().includes('topic_id=topic-1'));
  await page.getByRole('option',{name:topic.name,exact:true}).click();
  await requested;
  await page.keyboard.press('Escape');
  await page.route('**/api/v1/assessments/mistakes?**', route => route.fulfill({json:{items:[],total:0,active_count:0,next_offset:null,assessments:[],topics:[]}}));
  await page.reload();
  await expect(page.getByRole('heading',{name:'Nothing to revisit here'})).toBeVisible();
  await page.getByRole('button',{name:'Practice my mistakes',exact:true}).click();
  await expect(page.getByRole('button',{name:'Generate practice',exact:true})).toBeDisabled();
});


test('mistakes stay mounted and cached across idle time and tab navigation', async ({page}) => {
  await fixture(page);
  await page.clock.install();
  let reads = 0;
  page.on('request', request => { if (request.url().includes('/assessments/mistakes?')) reads++; });
  await page.goto('/assessments?tab=mistakes&mistake_view=list');
  await expect(page.getByRole('group', {name:'Your answer'}).first()).toBeVisible();
  await page.locator('details').first().locator('summary').click();
  await page.clock.runFor(1000);
  const initial = reads;
  await page.clock.fastForward(180000);
  await page.evaluate(() => { window.dispatchEvent(new Event('focus')); window.dispatchEvent(new Event('online')); document.dispatchEvent(new Event('visibilitychange')); });
  await page.clock.runFor(1000);
  expect(reads).toBe(initial);
  await expect(page.locator('details').first()).toHaveAttribute('open','');
  await page.getByRole('tab', {name:'Assessments', exact:true}).click();
  await page.getByRole('tab', {name:'Practice my mistakes', exact:true}).click();
  await expect(page.getByRole('group', {name:'Your answer'}).first()).toBeVisible();
  expect(reads).toBe(initial);
});

test('legacy Progress mistake links redirect with filters and active job intact', async ({page}) => {
  await fixture(page);
  await page.route('**/api/v1/assessments/generation-jobs/saved-job', route => route.fulfill({json:{id:'saved-job',state:'failed',title:'Revision assessment',completed_parts:0,total_parts:2,result:null,error:'Try again',can_retry:true}}));
  await page.goto('/progress?tab=mistakes&mistake_assessment=paper-1&mistake_topic=topic-1&revision_job=saved-job');
  await expect(page).toHaveURL('/assessments?tab=mistakes&mistake_assessment=paper-1&mistake_topic=topic-1&revision_job=saved-job');
  await expect(page.getByRole('tab',{name:'Practice my mistakes'})).toHaveAttribute('aria-selected','true');
  await expect(page.getByText('1 to revisit · 0 corrected')).toBeVisible();
});

test('only relevant same-owner changes refresh mistakes without replacing the cards', async ({page}) => {
  await fixture(page);
  let reads=0;
  page.on('request', request => { if(request.url().includes('/assessments/mistakes?')) reads++; });
  await page.goto('/assessments?tab=mistakes&mistake_view=list');
  await expect(page.getByRole('group',{name:'Your answer'}).first()).toBeVisible();
  await page.locator('details').first().locator('summary').click();
  const initial=reads;
  await page.evaluate(() => { const channel=new BroadcastChannel('mentra-pages-polish-user'); channel.postMessage(['notifications']); channel.close(); });
  await page.waitForTimeout(100);
  expect(reads).toBe(initial);
  let release!: () => void;
  const gate=new Promise<void>(resolve => { release=resolve; });
  await page.route('**/api/v1/assessments/mistakes?**', async route => { await gate; await route.fallback(); });
  await page.evaluate(() => { const channel=new BroadcastChannel('mentra-pages-polish-user'); channel.postMessage(['assessments']); channel.close(); });
  await expect.poll(() => reads).toBe(initial+1);
  await expect(page.getByRole('group',{name:'Your answer'}).first()).toBeVisible();
  await expect(page.locator('details').first()).toHaveAttribute('open','');
  release();
  await expect(page.getByRole('button',{name:'Practice my mistakes',exact:true})).toBeEnabled();
});
