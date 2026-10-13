import { test, expect, type Page } from '@playwright/test';
import { cachedPage, invalidatePageCache, setPageCacheOwner, cacheablePage } from '../src/services/pageCache';
import { errorMessage } from '../src/services/userError';

test('cache deduplication, expiry, invalidation and account isolation', async () => {
  setPageCacheOwner('a'); let calls = 0; const load = async () => ++calls;
  expect(await Promise.all([cachedPage('x', load), cachedPage('x', load)])).toEqual([1,1]);
  expect(await cachedPage('x', load)).toBe(1);
  const now = Date.now; Date.now = () => now() + 31_000;
  try { expect(await cachedPage('x', load)).toBe(2); } finally { Date.now = now; }
  invalidatePageCache(); expect(await cachedPage('x', load)).toBe(3);
  setPageCacheOwner('b'); expect(await cachedPage('x', load)).toBe(4);
  expect(cacheablePage('/api/v1/conversations/a/status', {})).toBe(false);
  expect(cacheablePage('/api/v1/assessments/attempts/a', {})).toBe(false);
  expect(cacheablePage('/api/v1/documents', {})).toBe(true);
});
test('aborted consumers and stale requests cannot poison shared cache', async () => {
  invalidatePageCache(); const controller = new AbortController(); let resolve!: (n: number) => void;
  const a = cachedPage('cancel', () => new Promise<number>(done => { resolve = done; }), controller.signal);
  const b = cachedPage('cancel', async () => 99);
  const rejection = expect(a).rejects.toMatchObject({name:'AbortError'});
  await Promise.resolve(); controller.abort(); resolve(5); await rejection; expect(await b).toBe(5);
  const stale = cachedPage('race', () => new Promise<number>(done => { resolve = done; }));
  await Promise.resolve(); invalidatePageCache(); resolve(9); await stale;
  expect(await cachedPage('race', async () => 10)).toBe(10);
  await expect(cachedPage('fail', async () => { throw Error('failed'); })).rejects.toThrow();
  expect(await cachedPage('fail', async () => 6)).toBe(6);
  let n=0; const job=async () => ({jobs:[{state:'RUNNING', attempt:++n}]});
  await cachedPage('job',job); await cachedPage('job',job); expect(n).toBe(2);
});
test('errors explain outcomes', () => {
  expect(errorMessage(502,'AI_PROVIDER_ERROR')).toBe('Mentra couldn’t finish this response. Please try again.');
  expect(errorMessage(500,'UNKNOWN')).toBe('Mentra could not complete this request.');
});

async function mockApp(page: Page, delay=0) {
  const counts: Record<string,number>={};
  await page.route('**/api/v1/**',async route => {
    const path=new URL(route.request().url()).pathname; counts[path]=(counts[path]??0)+1;
    if(delay) await new Promise(done => setTimeout(done,delay));
    let body: unknown=[];
    if(path.endsWith('/auth/me')) body={learner_id:'loading-test',username:'tester',user_id:null,provider:null};
    else if(path.endsWith('/student-profile')) body={learner_id:'loading-test',details:{education_level:'college',field_of_study:'Math',learning_goal:'Learn',learning_preference:'balanced',explanation_depth:'standard'},estimates:Object.fromEntries(['overall_proficiency','reasoning','quantitative','comprehension','domain_familiarity'].map(key => [key,{value:null,confidence:0,evidence_count:0}])),onboarding_phase:'complete',calibration_status:'skipped',evaluation_status:'not_started',version:1,context_version:1};
    else if(path.endsWith('/conversations/sync')) body={reset:false,cursor:1,has_more:false,conversations:[],deleted_ids:[],list_cursor:null};
    else if(path.endsWith('/documents')) body={items:[],total:0,limit:30,offset:0};
    else if(path.endsWith('/assessments/preferences')) body={auto_add:false,revision:1};
    else if(path.endsWith('/assessments')) body={items:[],next_offset:null};
    else if(path.endsWith('/notifications/preferences')) body={enabled:true,disabled_kinds:[],revision:1};
    else if(path.endsWith('/notifications/unread-count')) body={count:0};
    else if(path.endsWith('/notifications')) body={items:[],next_cursor:null};
    else if(path.endsWith('/learning/understanding')) body={items:[],total:0,total_concepts:0,limit:10,offset:0,generated_at:'2026-10-13T00:00:00Z'};
    else if(path.endsWith('/learning')) body={learner:{concepts:[]},recommendations:[],verification:[]};
    else if(path.endsWith('/events')) body={items:[],next_cursor:null};
    else if(path.endsWith('/memories/preferences')) body={automatic_memory:true,revision:1};
    else if(path.endsWith('/memories')) body={items:[],next_cursor:null};
    else if(path.endsWith('/rag/capabilities')) body={uploads_enabled:true,max_upload_bytes:1000000,formats:['pdf']};
    await route.fulfill({json:body});
  }); return counts;
}
for(const theme of ['light','dark']) test(`loading and navigation cache in ${theme}`,async ({page}) => {
  await page.addInitScript(theme => localStorage.setItem('mentra-theme',theme),theme);
  const counts=await mockApp(page,300); await page.goto('/library');
  await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
  await expect(page.getByRole('heading',{name:'Library',exact:true})).toBeVisible();
  await expect(page.getByRole('status',{name:'Loading',exact:true}).first()).toBeVisible();
  await expect(page.getByRole('heading',{name:'Your next source starts here'})).toBeVisible();
  const before=counts['/api/v1/documents'];
  await page.getByRole('link',{name:'Assessments',exact:true}).click();
  await expect(page.getByRole('status',{name:'Loading',exact:true}).first()).toBeVisible();
  await expect(page.getByText('Create your first assessment')).toBeVisible();
  await page.getByRole('link',{name:'Library',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Your next source starts here'})).toBeVisible();
  expect(counts['/api/v1/documents']).toBe(before);
  await page.goto('/settings?tab=notifications');
  await expect(page.getByRole('switch',{name:'Enable notifications',exact:true})).toBeVisible();
  expect(await page.locator('body').innerText()).not.toMatch(/Loading.*[.…]/);
});
test('data loaders cover settings, progress, notifications, upload form and mobile', async ({page}) => {
  await page.setViewportSize({width:390,height:844}); await mockApp(page,600);
  const pages=[['/settings?tab=memories','A fresh start'],['/progress','Every step builds understanding'],['/progress?tab=events','Room for your next plan'],['/notifications','No notifications'],['/library/new','Upload']];
  for(const [url,ready] of pages) {
    await page.goto(url);
    await expect(page.getByRole('status',{name:'Loading',exact:true}).first()).toBeVisible();
    if(url==='/notifications') await expect(page.getByRole('heading',{name:'A clear inbox'})).toBeVisible();
    else if(url==='/library/new') await expect(page.getByRole('button',{name:/Upload/}).first()).toBeVisible();
    else await expect(page.getByText(ready,{exact:false}).first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
});
test('chat opening shows skeleton and revisiting an empty chat uses its existing store',async ({page}) => {
  await mockApp(page,400);
  const chat={id:'empty-chat',title:'Empty chat',revision:1,message_count:0,selection:{mode:'AUTO',context_ids:[],document_ids:[],include_archived:false},created_at:'2026-10-11T00:00:00Z',updated_at:'2026-10-11T00:00:00Z',deleted_at:null};
  let opens=0;
  await page.route('**/api/v1/conversations/sync*',async route => {await new Promise(done => setTimeout(done,1400)); await route.fulfill({json:{reset:false,cursor:1,has_more:false,conversations:[chat],deleted_ids:[],list_cursor:null}});});
  await page.route('**/api/v1/conversations/empty-chat/status*',async route => {opens++; await new Promise(done => setTimeout(done,600)); await route.fulfill({json:{conversation:chat,items:[],has_more:false,next_cursor:null,turn:null}});});
  await page.goto('/');
  await expect(page.getByRole('region',{name:'Conversation history'}).locator('.animate-pulse')).toBeVisible();
  await page.getByRole('link',{name:'Empty chat',exact:true}).click();
  await expect(page.getByRole('region',{name:'Chat workspace'}).getByRole('status',{name:'Loading'}).first()).toBeVisible();
  await expect(page.getByRole('button',{name:'Send message'})).toBeVisible();
  await expect.poll(() => opens).toBe(1);
  await expect(page.getByRole('region',{name:'Chat workspace'}).getByRole('status',{name:'Loading'})).toHaveCount(0);
  await page.getByRole('link',{name:'Library',exact:true}).click();
  await page.getByRole('link',{name:'Empty chat',exact:true}).click();
  await expect(page.getByRole('button',{name:'Send message'})).toBeVisible(); await expect.poll(() => opens).toBe(2);
  await page.getByRole('button',{name:'Start a new chat'}).click();
  await expect(page).toHaveURL(/\/$/); await expect(page.getByRole('button',{name:'Send message'})).toBeVisible();
});
test('technical errors are hidden',async ({page}) => {
  await mockApp(page);
  await page.route('**/api/v1/documents?**',route => route.fulfill({status:502,json:{error:{code:'AI_PROVIDER_ERROR',message:'Check provider configuration and API key'}}}));
  await page.goto('/library');
  await expect(page.getByRole('alert')).toContainText('Mentra couldn’t finish this response. Please try again.');
  await expect(page.locator('body')).not.toContainText('API key');
});
test('successful writes and manual reload refresh cached API data',async ({page}) => {
  const counts=await mockApp(page); await page.goto('/library');
  await expect(page.getByRole('heading',{name:'Your next source starts here'})).toBeVisible();
  const before=counts['/api/v1/documents'];
  await page.evaluate(async () => {
    const path='/src/services/api.ts'; const {apiRequest}=await import(path);
    await apiRequest('/api/v1/documents?offset=0&archived=false');
  });
  expect(counts['/api/v1/documents']).toBe(before);
  await page.evaluate(async () => {
    const path='/src/services/api.ts'; const {apiRequest}=await import(path);
    await apiRequest('/api/v1/learning-contexts',{method:'POST',body:JSON.stringify({name:'New context'})});
    await apiRequest('/api/v1/documents?offset=0&archived=false');
  });
  expect(counts['/api/v1/documents']).toBe(before+1);
  await page.evaluate(async () => {
    const path='/src/services/api.ts'; const {apiRequest}=await import(path);
    await apiRequest('/api/v1/documents?offset=0&archived=false',{cache:'reload'});
  });
  expect(counts['/api/v1/documents']).toBe(before+2);
});
