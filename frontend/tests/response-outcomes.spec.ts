import {test, expect} from '@playwright/test';
import {workspace} from './renovation-fixtures';

test('a failed background task keeps useful content and retries the job through the composer', async ({page}) => {
  await workspace(page);
  let retried=false, retries=0, sends=0;
  const conversation={id:'polish-chat',title:'A learning conversation',revision:2,message_count:40,selection:{mode:'STANDARD'},
    created_at:'2026-10-11T00:00:00Z',updated_at:'2026-10-11T00:00:00Z',deleted_at:null};
  const outcome=()=>({version:3,state:retried?'in_progress':'partial',retryable:!retried,
    tasks:[{id:'receipt1',job_id:'job-1',job_kind:'generation',job_revision:retried?6:5}],
    control_action:retried?null:{kind:'generation_retry',id:'job-1',revision:5}});
  await page.route('**/api/v1/conversations/polish-chat/status**',route=>route.fulfill({json:{conversation,
    items:[{id:'message-39',conversation_id:'polish-chat',sequence:40,role:'assistant',content:'Your useful explanation is preserved.',
      created_at:conversation.created_at,response_outcome:outcome()}],has_more:false,next_cursor:null,
    turn:{id:'polish-turn',state:'SUCCEEDED',attempt:1,user_sequence:39,selection:{mode:'STANDARD'},error:null,
      can_retry:!retried,can_stop:retried,response_outcome:outcome(),control_action:outcome().control_action}}}));
  await page.route('**/api/v1/assessments/generation-jobs/job-1',route=>route.fulfill({json:{id:'job-1',state:'failed',
    title:'Practice',completed_parts:0,total_parts:3,result:null,error:'Generation failed.',can_retry:true,revision:5}}));
  await page.route('**/api/v1/assessments/generation-jobs/job-1/retry',route=>{
    retries++; retried=true; return route.fulfill({json:{id:'job-1',state:'queued',title:'Practice',completed_parts:0,
      total_parts:3,result:null,error:null,can_retry:false,revision:6}});
  });
  await page.route('**/api/v1/conversations/turns',route=>{sends++;return route.fulfill({status:500,json:{detail:'Unexpected new response'}});});
  await page.goto('/chat/polish-chat');
  await expect(page.getByText('Your useful explanation is preserved.',{exact:true})).toBeVisible();
  const retry=page.getByRole('button',{name:'Retry response',exact:true});
  await expect(retry).toBeEnabled();
  const input=page.getByRole('textbox',{name:'Ask Mentra anything'});
  await input.fill('A new question');
  await expect(page.getByRole('button',{name:'Send message',exact:true})).toBeEnabled();
  await input.fill('');
  await expect(retry).toBeEnabled();
  await retry.click();
  await expect.poll(()=>retries).toBe(1);
  await expect(page.getByRole('button',{name:'Pause response',exact:true})).toBeEnabled();
  expect(sends).toBe(0);
  await expect(page.getByText('Your useful explanation is preserved.',{exact:true})).toBeVisible();
});
