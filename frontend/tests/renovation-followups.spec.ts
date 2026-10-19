import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import type { Assessment, AssessmentAttempt } from '../src/types/assessments';

const created = '2026-10-17T00:00:00Z';
const question = (id: string) => ({ id, prompt:`Choose the force for ${id}.`, concept_ids:['concept'], marks:2, difficulty:.5,
  source_tokens:[], context:'Shared passage: the cart has mass 2 kg.', question_type:'mcq', answer_mode:'single_choice' as const,
  options:[{id:'a',label:'Four newtons'},{id:'b',label:'Two newtons'}] });
const source: Assessment = { id:'original-paper', context_id:'context-1', title:'Force practice', purpose:'practice', revision:1,
  created_at:created, sources:[], questions:['q1','q2','q3'].map(question) };
const result: AssessmentAttempt = { id:'original-attempt', assessment_id:source.id, revision:4, state:'graded', attempt_number:1,
  created_at:created, answers:{q1:'b',q2:'b',q3:'a'}, grades:source.questions.map((q,i) => ({question_id:q.id, score:i,
    confidence:1, feedback:'Review the definition.', concept_grades:{}, misconceptions:[], outcome:i===0?'wrong':i===1?'partial':'correct'})),
  extraction:null, error:null, evidence_status:'applied', grade_revision:1, grade_history:[] };

test('material search preserves a lost-response operation and payload edits receive a new ID', async ({page}) => {
  await workspace(page);
  const requests: Record<string, unknown>[] = [];
  await page.route('**/api/v1/assessments/generation-jobs', route => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({status:503, json:{error:{code:'UNAVAILABLE',message:'Lost response'}}});
  });
  await page.goto('/assessments?tab=create');
  await page.getByLabel('Topic', {exact:true}).fill('Mechanics');
  const generate = page.getByRole('button', {name:'Generate assessment', exact:true});
  await generate.click();
  await expect(page.getByRole('alert').first()).toBeVisible();
  await page.getByText('Study materials', {exact:false}).click();
  await page.getByRole('searchbox', {name:'Search assessment materials'}).fill('مرحبا');
  await page.getByText('Study materials', {exact:false}).click();
  await generate.click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].client_request_id).toBe(requests[0].client_request_id);
  await expect(generate).toBeEnabled();
  await page.getByLabel('Topic', {exact:true}).fill('New target');
  await generate.click();
  await expect.poll(() => requests.length).toBe(3);
  expect(requests[2].client_request_id).not.toBe(requests[1].client_request_id);
});

test('unavailable selected materials remain visible and are not silently dropped', async ({page}) => {
  await workspace(page);
  const doc = {id:'ready',title:'Ready material',filename:'ready.txt',active_generation_id:'gen',archived:false,context_ids:[],jobs:[]};
  await page.route('**/api/v1/documents**', route => new URL(route.request().url()).pathname.endsWith('/missing')
    ? route.fulfill({status:404,json:{error:{code:'NOT_FOUND',message:'Missing'}}})
    : route.fulfill({json:{items:[doc],total:1,limit:25,offset:0}}));
  await page.goto('/assessments?tab=create&document=missing');
  await page.getByLabel('Topic', {exact:true}).fill('Forces');
  const picker=page.getByRole('combobox',{name:'Assessment study documents',exact:true});
  await picker.click();
  await expect(page.getByRole('option',{name:'Selected material (unavailable or loading)',exact:true})).toHaveAttribute('aria-selected','true');
  await page.getByRole('option',{name:'Ready material',exact:true}).click();
  await page.keyboard.press('Escape');
  await expect(page.getByText('2 selected · Choose up to 20 ready materials. Selections stay when you search or change pages.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Generate assessment',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Clear selected materials'}).click();
  await expect(page.getByRole('button',{name:'Generate assessment',exact:true})).toBeEnabled();
});

test('assessment results link to the dedicated filtered mistake workspace', async ({page}) => {
  await workspace(page);
  await page.route('**/api/v1/assessments/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/original-paper/attempts')) return route.fulfill({json:[result]});
    if (path.endsWith('/original-paper')) return route.fulfill({json:source});
    if (path.endsWith('/mistakes')) return route.fulfill({json:{items:[],total:0,active_count:0,next_offset:null,assessments:[],topics:[]}});
    return route.fallback();
  });
  await page.goto(`/assessments?assessment=${source.id}&attempt=${result.id}`);
  await page.getByRole('link',{name:'Review these mistakes'}).click();
  await expect(page).toHaveURL(/tab=mistakes&mistake_assessment=original-paper/);
  await expect(page.getByRole('heading',{name:'Turn mistakes into progress'})).toBeVisible();
});

for (const variant of [{width:360,height:740,theme:'light'},{width:390,height:844,theme:'dark'},{width:1440,height:1000,theme:'light'}] as const) test(`progress evidence at ${variant.width} ${variant.theme} opens the specific owned attempt`, async ({page},info) => {
  await workspace(page,false,true);
  await page.setViewportSize(variant);
  await page.addInitScript(theme=>localStorage.setItem('mentra-theme',theme),variant.theme);
  await page.route('**/api/v1/learning/understanding/forces*', route => route.fulfill({json:{concept_id:'forces',context_id:'context-1',name:'Forces',knowledge_status:'developing',mastery:.6,
    mastery_lower_bound:.25,mastery_upper_bound:.85,independent_item_count:3,evidence_count:8,last_practice_at:created,last_independent_at:created,recommended_difficulty:.4,
    next_check:'Try new questions without hints.',difficulty_coverage:[{band:'easy',independent_items:3},{band:'medium',independent_items:0},{band:'hard',independent_items:0}],
    recent_evidence:[{occurred_at:created,source_type:'QUIZ',result:'CORRECT',difficulty:.4,independent:false,participation:'repeated',assessment_id:source.id,attempt_id:result.id,grade_revision:1,source_available:true},
      {occurred_at:created,source_type:'QUIZ',result:'CORRECT',difficulty:.4,independent:false,participation:'assisted',assessment_id:'deleted',attempt_id:'deleted-attempt',grade_revision:1,source_available:false}],generated_at:created}}));
  await page.route('**/api/v1/assessments/original-paper/attempts', route => route.fulfill({json:[result]}));
  await page.route('**/api/v1/assessments/original-paper', route => route.fulfill({json:source}));
  await page.goto('/progress');
  await page.getByRole('button',{name:"What is Forces's estimate based on?",exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'What is this estimate based on?'});
  await expect(dialog.getByText('Repeated / answer-exposed practice · Correct')).toBeVisible();
  await expect(dialog.getByText('Assisted practice · Correct')).toBeVisible();
  await expect(dialog.getByText(/Source unavailable or has newer results/)).toBeVisible();
  await expect(dialog.getByRole('link',{name:'Open assessment results'})).toHaveCount(1);
  await page.screenshot({path:info.outputPath(`evidence-${variant.width}-${variant.theme}.png`),animations:'disabled'});
  await dialog.getByRole('link',{name:'Open assessment results'}).click();
  await expect(page).toHaveURL(/assessment=original-paper&attempt=original-attempt/);
  await expect(page.getByRole('heading',{name:'Your results',exact:true})).toBeVisible();
});
