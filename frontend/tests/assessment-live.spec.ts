import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { assessmentFixture } from './fixtures/assessment';
import type { GenerationJob } from '../src/types/assessments';

test('live provider public handoff renders real questions without extra hydration',async({page})=>{
  test.skip(!process.env.LIVE_PROVIDER_HANDOFF,'Run benchmark_assessment_provider.py first and provide its public handoff path.');
  const job=JSON.parse(readFileSync(process.env.LIVE_PROVIDER_HANDOFF!,'utf8')) as GenerationJob;
  const count=('assessment' in job.result!?job.result!.assessment:job.result!).questions.length;
  expect(job.state).toBe('completed');expect(job.hydration?.version).toBe(1);
  expect(JSON.stringify(job)).not.toContain('model_answer');expect(JSON.stringify(job)).not.toContain('correct_option_id');
  const state=await assessmentFixture(page);
  await page.route('**/api/v1/assessments/generation-jobs/handoff-job',route=>route.fulfill({json:{...job,id:'handoff-job',
    conversation_id:'handoff-chat',result:{...job.result,conversation_id:'handoff-chat'}}}));
  await page.reload();const quiz=state.quiz;
  await expect(quiz.getByText(`Question 1 of ${count}`,{exact:false})).toBeVisible();
  const typed=quiz.getByRole('textbox');
  if(await typed.count()) await typed.fill('A local answer.'); else await quiz.getByRole('radio').first().check();await quiz.getByRole('button',{name:'Next',exact:true}).click();
  await expect(quiz.getByText(`Question 2 of ${count}`,{exact:false})).toBeVisible();await quiz.getByRole('button',{name:'Back',exact:true}).click();
  if(await typed.count()) await expect(typed).toHaveValue('A local answer.'); else await expect(quiz.getByRole('radio').first()).toBeChecked();expect(state.writes).toEqual([]);
  expect(state.reads.filter(path=>path.includes('/chat-drafts/'))).toEqual([]);
});
