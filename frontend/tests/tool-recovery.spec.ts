import { test, expect, type Page } from '@playwright/test';

async function recoveryChat(page: Page, state: 'RUNNING' | 'SUCCEEDED' | 'FAILED') {
  const id = 'recovery-chat', turnId = 'recovery-turn';
  const selection = {mode:'STANDARD', context_ids:[], document_ids:[], include_archived:false};
  const conversation = {id, title:'Recovery test', revision:2, message_count:2, selection,
    created_at:'2026-10-11T00:00:00Z', updated_at:'2026-10-11T00:00:00Z', deleted_at:null};
  const user = {id:'user-message', conversation_id:id, sequence:1, role:'user', content:'Explain gravity', created_at:conversation.created_at};
  const answer = {id:'assistant-message', conversation_id:id, sequence:2, role:'assistant', content:'Gravity attracts masses.', created_at:conversation.created_at,
    tool_warnings:[{tool_name:'event_manage', code:'TOOL_TIMEOUT', message:'The event service did not respond.', task_impact:'required_for_part', effect_certainty:'unknown'}]};
  const snapshot = () => ({conversation, items:state === 'SUCCEEDED' ? [user, answer] : [user], has_more:false, next_cursor:null,
    turn:{id:turnId, state, attempt:1, selection, user_sequence:1, error:state === 'FAILED' ? 'The requested document could not be found. Select another document.' : null}});
  let event = {schema_version:1, conversation_id:id, turn_id:turnId, attempt:1, sequence:1, step_id:'read-step', tool_name:'event_lookup',
    user_message:'Reading your agenda failed. Retrying, attempt 2 of 3.', status:'retry_wait', tool_attempt:2, max_attempts:3, error_code:'TOOL_TIMEOUT'};
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/events') && path.includes('/turns/')) {
      await route.fulfill({contentType:'text/event-stream', body:`event: activity\ndata: ${JSON.stringify(event)}\n\n`});
      return;
    }
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {learner_id:'recovery-user', username:'tester', user_id:null, provider:null};
    else if (path.endsWith('/student-profile')) body = {learner_id:'recovery-user', details:{education_level:'college', field_of_study:'Math', learning_goal:'Learn', learning_preference:'balanced', explanation_depth:'standard'},
      estimates:Object.fromEntries(['overall_proficiency','reasoning','quantitative','comprehension','domain_familiarity'].map(key => [key,{value:null, confidence:0, evidence_count:0}])),
      onboarding_phase:'complete', calibration_status:'skipped', evaluation_status:'not_started', version:1, context_version:1};
    else if (path.endsWith('/conversations/sync')) body = {reset:false, cursor:1, has_more:false, conversations:[conversation], deleted_ids:[], list_cursor:null};
    else if (path.endsWith('/status')) body = snapshot();
    else if (path.endsWith('/documents')) body = {items:[], total:0, limit:30, offset:0};
    else if (path.endsWith('/assessments/preferences')) body = {auto_add:false, revision:1};
    else if (path.endsWith('/assessments')) body = {items:[], next_offset:null};
    else if (path.endsWith('/notifications/unread-count')) body = {count:0};
    else if (path.endsWith('/rag/capabilities')) body = {uploads_enabled:true, max_upload_bytes:1000000, formats:['pdf']};
    await route.fulfill({json:body});
  });
  await page.goto(`/chat/${id}`);
  return {finish: () => {state = 'SUCCEEDED';}, step: (tool_name: string, status: string, user_message: string) => {
    event = {...event, sequence:event.sequence + 1, step_id:`step-${event.sequence + 1}`, tool_name, status, user_message};
  }};
}

test('current activity replaces earlier steps and never renders internal labels', async ({page}) => {
  const chat = await recoveryChat(page, 'RUNNING');
  const activity = page.getByLabel('Current activity');
  await expect(activity).toContainText('Trying again');
  chat.step('profile_context', 'running', 'profile_context');
  await expect(activity.getByRole('status')).toHaveText('Thinking');
  await expect(activity).not.toContainText('profile_context');
  await expect(activity).not.toContainText('Checking your learning preferences');
  chat.step('assessment_generate', 'running', 'Dispatching assessment_generate through MCP');
  await expect(activity).toContainText('Creating your practice questions');
  await expect(activity).not.toContainText('Trying again');
  await expect(activity).not.toContainText('assessment_generate');
  chat.step('assessment_generate', 'completed', 'Successfully completed assessment_generate');
  await expect(activity.getByRole('status')).toHaveText('Thinking');
  await expect(activity).not.toContainText('Creating your practice questions');
  await expect(activity).not.toContainText('completed');
  chat.step('new_internal_operation', 'running', 'Executing SQL repository internal operation');
  await expect(activity.getByRole('status')).toHaveText('Thinking');
  await expect(activity).not.toContainText('SQL');
  await expect(activity).not.toContainText('new_internal_operation');
  await expect(activity.getByRole('status')).toHaveCount(1);
  await expect(activity.locator('details, ol, li')).toHaveCount(0);
});

test('retry progress is visible and permanent limitations survive refresh', async ({page}) => {
  const chat = await recoveryChat(page, 'RUNNING');
  await expect(page.getByLabel('Current activity').getByRole('status')).toContainText('Trying again');
  await expect(page.getByLabel('Current activity')).not.toContainText('event_lookup');
  await expect(page.getByLabel('Current activity')).not.toContainText('retry_wait');
  await expect(page.getByLabel('Current activity').locator('details, ol')).toHaveCount(0);
  chat.finish();
  await expect(page.getByLabel('Response limitations')).toContainText('Completion of this action has not been verified.');
  await expect(page.getByRole('article', {name:'Mentra response'})).toContainText('Gravity attracts masses.');
  await page.reload();
  await expect(page.getByLabel('Response limitations')).toContainText('The event service did not respond.');
});

test('canonical failure gives its specific safe next step and retry control', async ({page}) => {
  await recoveryChat(page, 'FAILED');
  await expect(page.getByRole('alert')).toContainText('Select another document.');
  await expect(page.getByRole('button', {name:'Retry response'})).toBeVisible();
});

test('successful chat remains readable with limitations on a narrow screen', async ({page}) => {
  await page.setViewportSize({width:390, height:844});
  await recoveryChat(page, 'SUCCEEDED');
  await expect(page.getByLabel('Response limitations')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
