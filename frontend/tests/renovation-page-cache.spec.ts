import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { cachedPage, invalidateMutation, invalidatePageCache, setPageCacheOwner } from '../src/services/pageCache';

test('page cache deduplicates navigation, bounds staleness and isolates owners', async () => {
  setPageCacheOwner('cache-test');
  let reads = 0;
  const load = async () => ++reads;
  const key = '/api/v1/assessments?offset=0[]';
  expect(await cachedPage(key, load)).toBe(1);
  const now = Date.now;
  Date.now = () => now() + 15_000;
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
  finish('old'); await expect(old).rejects.toThrow('Aborted');
  expect(await cachedPage(key, async () => 'unexpected')).toBe('new');
  setPageCacheOwner(null);
});

test('canceling one consumer preserves a shared read and idle entries expire on next navigation', async () => {
  setPageCacheOwner('shared-cancel');
  const first = new AbortController();
  let finish!: (value: string) => void;
  let reads = 0;
  const load = () => { reads++; return new Promise<string>(resolve => { finish = resolve; }); };
  const key = '/api/v1/learning/page[]';
  const canceled = cachedPage(key, load, first.signal);
  const foreground = cachedPage(key, load);
  await Promise.resolve();
  first.abort();
  await expect(canceled).rejects.toThrow('Aborted');
  finish('current');
  expect(await foreground).toBe('current');
  expect(reads).toBe(1);
  const now = Date.now;
  Date.now = () => now() + 31_000;
  try { expect(await cachedPage(key, async () => 'refreshed')).toBe('refreshed'); } finally { Date.now = now; }
  setPageCacheOwner(null);
});

test('Memories loads only its own list and preferences, with no Library request', async ({ page }) => {
  await workspace(page);
  const paths: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/v1/')) paths.push(new URL(request.url()).pathname); });
  await page.goto('/settings?tab=memories');
  await expect(page.getByText('A fresh start', { exact: true })).toBeVisible();
  expect(paths.filter(path => path.startsWith('/api/v1/memories'))).toEqual(['/api/v1/memories/page']);
  expect(paths.some(path => path.startsWith('/api/v1/documents'))).toBe(false);
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
  await page.route('**/api/v1/assessments/page?**', route => route.fulfill({json:{items:[
    {id:'graded',title:'Graded paper',questions:[],purpose:'practice',attempt_summary:{count:2,latest_state:'graded',graded_attempt_id:'attempt-2',correct:3,incorrect:2,partial:1}},
    {id:'new',title:'Fresh paper',questions:[],purpose:'practice',attempt_summary:{count:0,latest_state:null,graded_attempt_id:null,correct:0,incorrect:0,partial:0}},
    {id:'pending',title:'Pending paper',questions:[],purpose:'practice',attempt_summary:{count:1,latest_state:'submitted',graded_attempt_id:null,correct:0,incorrect:0,partial:0}},
  ],next_offset:null,contexts:[],detail:null,attempts:[]}}));
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
  await page.route('**/api/v1/documents/page?**', route => {
    reads++;
    return route.fulfill({json:{items:[{id:'processing',title:'Processing notes',filename:'notes.pdf',context_ids:[],archived:false,active_generation_id:completed ? 'generation' : null,jobs:completed ? [] : [{id:'job',state:'RUNNING'}]}],total:1,offset:0,limit:30,contexts:[]}});
  });
  await page.goto('/library');
  await expect(page.getByText('Preparing',{exact:true})).toBeVisible();
  completed = true;
  await page.clock.runFor(3500);
  await expect(page.getByText('Ready',{exact:true})).toBeVisible();
  // Completion invalidates dependent material views once. Wait for that
  // revalidation before measuring the absence of further polling.
  await expect.poll(async () => { await page.clock.runFor(100); return reads; }).toBe(3);
  const final = reads;
  await page.clock.fastForward(180000);
  await page.clock.runFor(1000);
  expect(reads).toBe(final);
  await expect(page.getByRole('link',{name:'Processing notes',exact:true})).toBeVisible();
});
