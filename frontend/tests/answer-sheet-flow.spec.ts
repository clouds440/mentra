import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { chooseOption } from './select-helpers';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

// Real auth, Files intake, parsing, submission and worker persistence. Only the
// test server's AI model and remote file provider are deterministic substitutes.
for (const kind of ['txt','pdf']) test(`real ${kind} answer-sheet upload grades and survives reload`, async ({page}) => {
  test.setTimeout(90_000);
  await page.goto('/register');
  await page.getByLabel('Username',{exact:true}).fill(`answers_${randomUUID().slice(0,8)}`);
  await page.getByLabel('Password',{exact:true}).fill('an isolated answer sheet integration password');
  await page.getByRole('button',{name:'Create account',exact:true}).click();
  await finishOnboardingWithoutAssessment(page);
  const base='http://127.0.0.1:18003/api/v1', headers={Origin:'http://127.0.0.1:15173'};
  const created=await page.request.post(`${base}/learning-contexts`,{headers,data:{name:'Forces',activate:true}});
  expect(created.ok()).toBe(true); const context=await created.json();
  const generated=await page.request.post(`${base}/assessments`,{headers,data:{client_request_id:randomUUID(),context_id:context.context_id,topic:'Forces',concept_names:['Force'],confirm_new_concepts:true,count:2,question_format:kind==='txt' ? 'mcq':'written'}});
  expect(generated.ok(),await generated.text()).toBe(true); const assessment=await generated.json();
  await page.goto(`/assessments?assessment=${assessment.id}`);
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download question paper PDF',exact:true}).click();
  expect((await download).suggestedFilename()).toMatch(/question-paper\.pdf$/);
  if (kind==='txt') await page.getByLabel('Upload assessment answer sheet').setInputFiles({name:'answers.txt',mimeType:'text/plain',buffer:Buffer.from('1. A\n2. B')});
  else await page.getByLabel('Upload assessment answer sheet').setInputFiles(fileURLToPath(new URL('./fixtures/assessment-answers.pdf',import.meta.url)));
  const sheet=page.getByRole('region',{name:'Assessment answer sheet'});
  await expect(sheet.getByRole('button',{name:'Confirm text & submit'})).toBeDisabled();
  await chooseOption(sheet.getByLabel('Assistance used',{exact:true}),kind==='txt' ? 'assisted':'independent');
  await sheet.getByRole('switch',{name:'I reviewed and corrected all extracted answers'}).check();
  await sheet.getByRole('button',{name:'Confirm text & submit'}).click();
  await expect(sheet.getByText('Attempt 1 · Attempted',{exact:true})).toBeVisible({timeout:30_000});
  await expect(sheet.getByRole('region',{name:'Assessment feedback'})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button',{name:'Review result'})).toHaveCount(2);
  const history=await page.request.get(`${base}/assessments/${assessment.id}/attempts`);
  const attempts=await history.json();
  expect(attempts).toHaveLength(1); expect(attempts[0].state).toBe('graded'); expect(attempts[0].grades).toHaveLength(2);
  expect(attempts[0].reported_assistance).toBe(kind==='txt' ? 'assisted':'independent');
  expect(attempts[0].scoring.multiplier).toBe(kind==='txt' ? .9:1);
  expect(attempts[0].scoring.adjusted_score).toBe(Number((attempts[0].scoring.raw_score*(kind==='txt' ? .9:1)).toFixed(4)));
});
