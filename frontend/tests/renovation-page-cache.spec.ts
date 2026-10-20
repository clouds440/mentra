import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { cachedPage, invalidateMutation, invalidatePageCache, setPageCacheOwner } from '../src/services/pageCache';

test('page cache stays until a relevant successful mutation and isolates owners', async () => {
  setPageCacheOwner('cache-test');
  let reads = 0;
  const load = async () => ++reads;
  const key = '/api/v1/assessments?offset=0[]';
  expect(await cachedPage(key, load)).toBe(1);
  const now = Date.now;
  Date.now = () => now() + 86400000;
  try { expect(await cachedPage(key, load)).toBe(1); } finally { Date.now = now; }
  invalidateMutation('/api/v1/notifications/item');
  expect(await cachedPage(key, load)).toBe(1);
  invalidateMutation('/api/v1/events/preview');
  expect(await cachedPage(key, load)).toBe(1);
  invalidateMutation('/api/v1/assessments/attempts/attempt/submission');
  expect(await cachedPage(key, load)).toBe(2);
  setPageCacheOwner('different-user');
  expect(await cachedPage(key, load)).toBe(3);
  setPageCacheOwner(null);
});

test('invalidation cannot let an older pending read repopulate the cache', async () => {
  setPageCacheOwner('race-test');
  let finish!: (value: string) => void;
  const key = '/api/v1/learning[]';
  const old = cachedPage(key, () => new Promise<string>(resolve => { finish = resolve; }));
  await Promise.resolve();
  invalidatePageCache(['learning']);
  expect(await cachedPage(key, async () => 'new')).toBe('new');
  finish('old'); await old;
  expect(await cachedPage(key, async () => 'unexpected')).toBe('new');
  setPageCacheOwner(null);
});

for (const [route, visible] of [
  ['/library', 'Motion and forces'],
  ['/assessments', 'Understanding forces'],
  ['/progress', 'Your understanding'],
  ['/progress?tab=events', 'Physics study session'],
  ['/notifications', 'Time for a little physics'],
  ['/settings?tab=notifications', 'Settings'],
  ['/settings?tab=memories', 'A fresh start'],
] as const) {
  test(`settled ${route} does not reload on time, focus or reconnect`, async ({page}) => {
    await workspace(page, false, true);
    await page.route('**/api/v1/memories?**', route => route.fulfill({json:{items:[],next_cursor:null}}));
    await page.route('**/api/v1/memories/preferences', route => route.fulfill({json:{automatic_memory:false,revision:1}}));
    await page.clock.install();
    const reads: string[] = [];
    page.on('request', request => {
      const path = new URL(request.url()).pathname;
      if (/\/api\/v1\/(documents|learning|assessments|events|event-proposals|memories|notifications)/.test(path)) reads.push(request.url());
    });
    await page.goto(route);
    await expect(page.getByText(visible, {exact:true}).first()).toBeVisible();
    await page.clock.runFor(1000);
    const initial = [...reads];
    await page.clock.fastForward(180000);
    await page.evaluate(() => {
      window.dispatchEvent(new Event('focus')); window.dispatchEvent(new Event('online'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.clock.runFor(1000);
    expect(reads).toEqual(initial);
    await expect(page.getByText(visible, {exact:true}).first()).toBeVisible();
  });
}

test('assessment cards show graded counts and distinguish ungraded attempts', async ({page}) => {
  await workspace(page, false, true);
  await page.setViewportSize({width:320,height:900});
  await page.route('**/api/v1/assessments?**', route => route.fulfill({json:{items:[
    {id:'graded',title:'Graded paper',questions:[],purpose:'practice',attempt_summary:{count:2,latest_state:'graded',graded_attempt_id:'attempt-2',correct:3,incorrect:2,partial:1}},
    {id:'new',title:'Fresh paper',questions:[],purpose:'practice',attempt_summary:{count:0,latest_state:null,graded_attempt_id:null,correct:0,incorrect:0,partial:0}},
    {id:'pending',title:'Pending paper',questions:[],purpose:'practice',attempt_summary:{count:1,latest_state:'submitted',graded_attempt_id:null,correct:0,incorrect:0,partial:0}},
  ],next_offset:null}}));
  await page.goto('/assessments');
  const graded=page.getByRole('button').filter({hasText:'Graded paper'});
  await expect(graded).toContainText('3 correct'); await expect(graded).toContainText('2 incorrect');
  await expect(graded).toContainText('1 partially correct');
  await expect(page.getByRole('button').filter({hasText:'Fresh paper'})).toContainText('No attempts yet');
  await expect(page.getByRole('button').filter({hasText:'Pending paper'})).toContainText('Awaiting grading');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('material processing updates until completion and then stops polling', async ({page}) => {
  await workspace(page, false, true);
  await page.clock.install();
  let completed = false, reads = 0;
  await page.route('**/api/v1/documents?**', route => {
    reads++;
    return route.fulfill({json:{items:[{id:'processing',title:'Processing notes',filename:'notes.pdf',context_ids:[],archived:false,active_generation_id:completed ? 'generation' : null,jobs:completed ? [] : [{id:'job',state:'RUNNING'}]}],total:1,offset:0,limit:30}});
  });
  await page.goto('/library');
  await expect(page.getByText('Preparing',{exact:true})).toBeVisible();
  completed = true;
  await page.clock.runFor(3500);
  await expect(page.getByText('Ready',{exact:true})).toBeVisible();
  await page.clock.runFor(3500);
  const final = reads;
  await page.clock.fastForward(180000);
  await page.clock.runFor(1000);
  expect(reads).toBe(final);
  await expect(page.getByRole('link',{name:'Processing notes',exact:true})).toBeVisible();
});
