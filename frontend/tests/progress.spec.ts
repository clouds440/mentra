import { test, expect, type Page } from '@playwright/test';

async function progress(page: Page, options: {failOnce?:string; reviews?:boolean} = {}) {
  const date = '2026-10-13T10:00:00Z';
  const topics = Array.from({length:25}, (_, i) => ({concept_id:`topic-${i}`, name:`AI models ${String(i).padStart(2,'0')}`,
    knowledge_status:i ? 'developing' : 'insufficient_evidence', mastery:i ? .6 : null, estimate_confidence:i ? .5 : null, retention_confidence:i ? .4 : null, misconceptions:[]}));
  let pending = ['Training', 'Fine-tuning', 'Model evaluation'].map((label, i) => ({id:`candidate-${i}`, label, context_id:'ai'}));
  const writes: {id:string; decision:string}[] = [];
  let fail = options.failOnce;
  let reviewGate: Promise<void> | null = null, releaseReview = () => {};
  let searchGate: Promise<void> | null = null, releaseSearch = () => {};
  const requests: URL[] = [];
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {learner_id:'progress-user', username:'learner', user_id:null, provider:null};
    else if (path.endsWith('/student-profile')) body = {learner_id:'progress-user',details:{education_level:'college',field_of_study:'AI',learning_goal:'Understand AI',learning_preference:'balanced',explanation_depth:'standard'}, estimates:Object.fromEntries(['overall_proficiency','reasoning','quantitative','comprehension','domain_familiarity'].map(key => [key,{value:null,confidence:0,evidence_count:0}])),onboarding_phase:'complete',calibration_status:'skipped',evaluation_status:'not_started',version:1,context_version:1};
    else if (path.endsWith('/conversations/sync')) body = {reset:false,cursor:1,has_more:false,conversations:[],deleted_ids:[],list_cursor:null};
    else if (path.endsWith('/learning-contexts')) body = [{context_id:'ai',name:'AI basics',status:'ACTIVE'}, {context_id:'physics',name:'Physics',status:'DORMANT'}];
    else if (path.endsWith('/concept-candidates')) body = pending;
    else if (path.includes('/concept-candidates/')) {
      const id = path.split('/').pop()!; const decision = request.postDataJSON().decision;
      writes.push({id, decision});
      if (reviewGate) await reviewGate;
      if (fail === id) { fail = undefined; return route.fulfill({status:503,json:{error:{code:'SERVICE_UNAVAILABLE',message:'Private technical diagnostic'}}}); }
      pending = pending.filter(item => item.id !== id); body = {status:decision === 'confirm' ? 'confirmed' : 'discarded', concept_id:decision === 'confirm' ? id : null};
    } else if (path.endsWith('/learning/understanding')) {
      requests.push(url);
      const query = url.searchParams.get('query')?.toLowerCase() ?? '';
      if (query === 'models 22' && searchGate) await searchGate;
      const all = url.searchParams.get('context_id') === 'physics' ? [{...topics[0], name:'Forces'}] : topics;
      const filtered = all.filter(item => item.name.toLowerCase().includes(query));
      const offset = Math.min(Number(url.searchParams.get('offset')), Math.max(0, Math.floor((filtered.length - 1)/10)*10));
      body = {items:filtered.slice(offset,offset+10), total:filtered.length, total_concepts:all.length, offset, limit:10, generated_at:date};
    } else if (path.endsWith('/learning')) body = {
      learner:{concepts:topics.slice(0,12),generated_at:date,context_ids:['ai']},
      recommendations:[{concept_id:'new',name:'Model training',reason:'insufficient_evidence',knowledge_status:'insufficient_evidence',recommended_difficulty:.3}, {concept_id:'unknown',name:'New topic',reason:'TRACE_private',knowledge_status:'developing',recommended_difficulty:.3}],
      verification:[{concept_id:'new',name:'New models',reason:'insufficient_evidence'}, {concept_id:'difficulty',name:'Fine-tuning difficulty',reason:'difficulty_unverified'}, ...(options.reviews ? [{concept_id:'mixed',name:'Transfer learning',reason:'contradictory_evidence'}] : [])],
    };
    await route.fulfill({json:body});
  });
  return {writes, requests,
    holdReviews() { reviewGate = new Promise<void>(resolve => { releaseReview = resolve; }); },
    releaseReviews() { releaseReview(); reviewGate = null; },
    holdSearch() { searchGate = new Promise<void>(resolve => { releaseSearch = resolve; }); },
    releaseSearch() { releaseSearch(); searchGate = null; },
  };
}

test('understanding pages cover the full collection with small page controls', async ({page}) => {
  await progress(page); await page.goto('/progress');
  const table = page.getByRole('table',{name:'Your understanding'});
  await expect(table.getByRole('row')).toHaveCount(11);
  await expect(page.getByText('Showing 1–10 of 25 topics')).toBeVisible();
  const pages = page.getByRole('navigation',{name:'Understanding pages'});
  await expect(pages.getByRole('button',{name:'Previous page'})).toBeDisabled();
  await pages.getByRole('button',{name:'Next page'}).click();
  await expect(page.getByText('Showing 11–20 of 25 topics')).toBeVisible();
  await pages.getByRole('button',{name:'Page 3',exact:true}).click();
  await expect(table.getByRole('row')).toHaveCount(6);
  await expect(page.getByText('Showing 21–25 of 25 topics')).toBeVisible();
  await expect(pages.getByRole('button',{name:'Page 3',exact:true})).toHaveAttribute('aria-current','page');
  await expect(pages.getByRole('button',{name:'Next page'})).toBeDisabled();
  await pages.getByRole('button',{name:'Previous page'}).click();
  await expect(page.getByText('Showing 11–20 of 25 topics')).toBeVisible();
});

test('search finds topics beyond page one, resets pages and explains empty results', async ({page}) => {
  await progress(page); await page.goto('/progress');
  await page.getByRole('button',{name:'Page 3',exact:true}).click();
  await page.getByRole('searchbox',{name:'Search your understanding'}).fill('models 24');
  await expect(page.getByText('Showing 1–1 of 1 topics')).toBeVisible();
  await expect(page.getByRole('table').getByText('AI models 24')).toBeVisible();
  await page.getByRole('searchbox').fill('no matching topic');
  await expect(page.getByRole('heading',{name:'No matching topics'})).toBeVisible();
  await page.getByRole('button',{name:'Clear topic search'}).click();
  await expect(page.getByText('Showing 1–10 of 25 topics')).toBeVisible();
  await page.getByRole('combobox',{name:'Learning context'}).click();
  await page.getByRole('option',{name:'Physics',exact:true}).click();
  await expect(page.getByRole('table').getByText('Forces',{exact:true})).toBeVisible();
  await expect(page.getByText('Showing 1–1 of 1 topics')).toBeVisible();
});

test('late search results cannot replace a newer query', async ({page}) => {
  const state = await progress(page); state.holdSearch(); await page.goto('/progress');
  await page.getByRole('searchbox').fill('models 22');
  await expect.poll(() => state.requests.some(url => url.searchParams.get('query') === 'models 22')).toBe(true);
  await page.getByRole('searchbox').fill('models 24');
  await expect(page.getByRole('table').getByText('AI models 24')).toBeVisible();
  state.releaseSearch();
  await expect(page.getByRole('table').getByText('AI models 22')).toHaveCount(0);
});

for (const action of ['Confirm','Dismiss']) test(`only ${action} loads for the selected suggestion`, async ({page}) => {
  const state = await progress(page); state.holdReviews(); await page.goto('/progress');
  const row = page.getByRole('group',{name:'Review Training',exact:true});
  const selected = row.getByRole('button',{name:action,exact:true});
  await selected.click(); await expect(selected).toHaveAttribute('aria-busy','true');
  await expect(row.getByRole('button',{name:action === 'Confirm' ? 'Dismiss' : 'Confirm',exact:true})).not.toHaveAttribute('aria-busy','true');
  await expect(page.getByRole('group',{name:'Review Fine-tuning',exact:true}).getByRole('button',{name:'Confirm',exact:true})).not.toHaveAttribute('aria-busy','true');
  state.releaseReviews(); await expect(row).toHaveCount(0);
  expect(state.writes).toEqual([{id:'candidate-0',decision:action === 'Confirm' ? 'confirm' : 'discard'}]);
});

test('Confirm all preserves successful decisions and retries only remaining suggestions', async ({page}) => {
  const state = await progress(page,{failOnce:'candidate-1'}); await page.goto('/progress');
  await page.getByRole('button',{name:'Confirm all suggestions'}).click();
  await expect(page.getByRole('alert')).toContainText('Confirmed topics were saved');
  await expect(page.getByRole('group',{name:'Review Training',exact:true})).toHaveCount(0);
  await expect(page.getByRole('group',{name:'Review Model evaluation',exact:true})).toHaveCount(0);
  await expect(page.getByRole('group',{name:'Review Fine-tuning',exact:true})).toBeVisible();
  expect(state.writes.map(item => item.id)).toEqual(['candidate-0','candidate-1','candidate-2']);
  await page.getByRole('button',{name:'Confirm all suggestions'}).click();
  await expect(page.getByRole('region',{name:'Concept suggestions'})).toHaveCount(0);
  expect(state.writes.map(item => item.id)).toEqual(['candidate-0','candidate-1','candidate-2','candidate-1']);
});

test('unsupported review stays hidden and every section has learner-facing explanations', async ({page}) => {
  await progress(page); await page.goto('/progress');
  await expect(page.getByRole('heading',{name:'Your understanding'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Check your understanding'})).toHaveCount(0);
  await expect(page.getByText('Getting started',{exact:true})).toBeVisible();
  await expect(page.getByText(/It doesn’t mark it learned or change your score/)).toBeVisible();
  await expect(page.getByText(/Start with a few practice questions/)).toBeVisible();
  await expect(page.getByText(/insufficient_evidence|difficulty_unverified|TRACE_private|Private technical/)).toHaveCount(0);
  await page.getByText('What do these estimates mean?',{exact:true}).click();
  await expect(page.getByText(/learning indicators, not exam grades/)).toBeVisible();
});

for (const theme of ['light','dark']) test(`meaningful review is actionable and responsive in ${theme}`, async ({page}, info) => {
  await page.setViewportSize({width:390,height:844});
  await page.addInitScript(theme => localStorage.setItem('mentra-theme',theme),theme);
  await progress(page,{reviews:true}); await page.goto('/progress');
  const reviews = page.getByRole('region',{name:'Check your understanding',exact:true});
  await expect(reviews.getByText('Transfer learning',{exact:true})).toBeVisible();
  await expect(reviews.getByText(/recent answers gave mixed results/)).toBeVisible();
  await expect(reviews.getByRole('link',{name:'Check this topic'})).toHaveAttribute('href',/practice=Transfer%20learning/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('progress-mobile.png'),fullPage:true});
});
