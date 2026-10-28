import { test, expect } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { chooseOption } from './select-helpers';

test('one-line prose and commands copy only their payload', async ({ page, context }, info) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const state = await workspace(page);
  state.complete('Use either artifact below.\n\n```text\nPlease send the revised timetable by Friday.\n```\n\n```bash\ngit status --short\n```');
  await page.goto('/chat/polish-chat');
  const reply = page.getByRole('article', { name: 'Mentra response' }).last();
  await reply.getByRole('button', { name: 'Copy text', exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('Please send the revised timetable by Friday.');
  await reply.getByRole('button', { name: 'Copy code', exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('git status --short');
  await page.screenshot({ path: info.outputPath('copyable-artifacts.png') });
});

test('quiz starter sends a complete request without an extra setup step', async ({ page }) => {
  await workspace(page, false, false, '', false, 0);
  await page.goto('/chat/polish-chat');
  const request = page.waitForRequest(req => req.url().endsWith('/conversations/turns') && req.method() === 'POST');
  await page.getByRole('button', { name: 'Quiz me', exact: true }).click();
  const body = (await request).postDataJSON();
  expect(body.content).toBe('Give me a short quiz to practice what I am learning.');
  expect(body.content).not.toContain('interactive');
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toHaveValue('');
});

test('study starter opens the real source picker without requiring @ syntax', async ({ page }) => {
  await workspace(page, false, true, '', false, 0);
  await page.goto('/chat/polish-chat');
  await page.getByRole('button', { name: 'Study my material', exact: true }).click();
  await expect(page.getByRole('listbox', { name: 'Study material', exact: true })).toBeVisible();
  await page.getByRole('option').filter({ hasText: 'Motion and forces' }).click();
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toHaveValue('');
  await expect(page.getByRole('button', { name: 'Choose study material', exact: true })).toBeVisible();
});

test('interactive delivery makes a written question directly answerable and preserves written override', async ({ page }, info) => {
  await workspace(page);
  const assessment = { id:'native-assessment',context_id:'context-1',title:'One question practice',purpose:'practice',revision:1,
    created_at:'2026-10-26T00:00:00Z',preferences:{delivery:'interactive'},sources:[],paper:null,
    questions:[{id:'native-question',question_type:'written',answer_mode:'text',prompt:'Explain why equal fractions can have different numerators.',
      concept_ids:['fractions'],difficulty:.4,marks:1,source_tokens:[],options:[]}] };
  const card = {id:'native-draft',assessment_id:null,conversation_id:'polish-chat',assessment};
  const status = {conversation:{id:'polish-chat',title:'Practice',revision:2,message_count:2,selection:{mode:'STANDARD'},created_at:assessment.created_at,updated_at:assessment.created_at},
    items:[{id:'native-request',conversation_id:'polish-chat',sequence:1,role:'user',content:'Give me 1 question quiz',created_at:assessment.created_at},
      {id:'native-reply',conversation_id:'polish-chat',sequence:2,role:'assistant',content:'One question practice',created_at:assessment.created_at,assessment_cards:[card]}],
    turn:{id:'native-turn',state:'SUCCEEDED',attempt:1,user_sequence:1,selection:{mode:'STANDARD'}},has_more:false,next_cursor:null};
  await page.route('**/api/v1/conversations/polish-chat/status*', route => route.fulfill({json:status}));
  await page.route('**/api/v1/assessments/chat-drafts/native-draft', route => route.fulfill({json:card}));
  await page.goto('/chat/polish-chat');
  const region = page.getByRole('region', { name: 'Chat assessment' });
  await expect(region.getByRole('textbox')).toBeVisible();
  await expect(region.getByRole('button', { name: /Add & answer|Answer in UI/ })).toHaveCount(0);
  await expect(region.getByText('Question 1 of 1')).toBeVisible();
  await page.screenshot({ path: info.outputPath('one-question-native-ui.png') });
  assessment.preferences.delivery = 'written';
  await page.reload();
  await expect(region.getByRole('textbox')).toHaveCount(0);
  await expect(region.getByRole('button', { name: 'Add & answer', exact:true })).toBeVisible();
});

test('source practice carries current document scope', async ({ page }) => {
  await workspace(page);
  const source = {token:'S1',document_id:'material-1',version_id:'v1',generation_id:'g1',chunk_id:'c1',title:'Motion and forces',heading_path:[],spans:[],excerpt:'Force is mass times acceleration.',warnings:[]};
  const created='2026-10-26T00:00:00Z';
  await page.route('**/api/v1/conversations/polish-chat/status*', route => route.fulfill({json:{
    conversation:{id:'polish-chat',title:'Study',revision:2,message_count:2,selection:{mode:'STANDARD'},created_at:created,updated_at:created},
    items:[{id:'u',sequence:1,role:'user',content:'Explain this source',created_at:created,conversation_id:'polish-chat'},
      {id:'a',sequence:2,role:'assistant',content:'Force relates mass and acceleration. [[S1]]',sources:[source],citations:['S1'],created_at:created,conversation_id:'polish-chat'}],
    turn:{id:'t',state:'SUCCEEDED',attempt:1,user_sequence:1,selection:{mode:'STANDARD'}},has_more:false,next_cursor:null}}));
  await page.goto('/chat/polish-chat');
  const request = page.waitForRequest(req => req.url().endsWith('/conversations/turns') && req.method() === 'POST');
  await page.getByRole('button', { name:'Practice this material',exact:true }).click();
  const body=(await request).postDataJSON();
  expect(body.retrieval.mode).toBe('SOURCE_SPECIFIC');
  expect(body.retrieval.document_ids).toEqual(['material-1']);
  expect(body.content).toContain('grounded only');
});

test('ordinary chat does not fetch Library lists until requested', async ({ page }) => {
  await workspace(page);
  const lists: string[]=[];
  page.on('request', request => { if (/\/api\/v1\/(?:documents|learning-contexts)(?:\?|$)/.test(request.url())) lists.push(request.url()); });
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('textbox',{name:'Ask Mentra anything'})).toBeEnabled();
  expect(lists).toEqual([]);
  await page.getByRole('button',{name:'Choose study material',exact:true}).click();
  await expect.poll(() => lists.length).toBe(2);
});

test('a durable assessment reference appears before narration completes', async ({ page }) => {
  await workspace(page,true);
  const created='2026-10-26T00:00:00Z';
  const card={id:'early-draft',assessment_id:null,conversation_id:'polish-chat',assessment:{
    id:'early-assessment',context_id:'context-1',title:'Ready while Mentra continues',purpose:'practice',revision:1,created_at:created,
    preferences:{delivery:'interactive'},paper:null,sources:[],questions:[{id:'early-question',question_type:'short_answer',answer_mode:'text',
      prompt:'What does acceleration measure?',concept_ids:['motion'],difficulty:.3,marks:1,source_tokens:[],options:[]}]}};
  let reads=0;
  await page.route('**/api/v1/assessments/chat-drafts/early-draft',route=>{reads++;return route.fulfill({json:card});});
  await page.route('**/api/v1/conversations/polish-chat/turns/polish-turn/events*',route=>route.fulfill({contentType:'text/event-stream',body:
    `event: activity\ndata: ${JSON.stringify({schema_version:1,conversation_id:'polish-chat',turn_id:'polish-turn',attempt:1,sequence:1,
      step_id:'assessment-result',status:'completed',tool_name:'assessment_generate',user_message:'Practice ready',
      assessment_card:{kind:'draft',id:'early-draft',title:card.assessment.title}})}\n\n`}));
  await page.goto('/chat/polish-chat');
  const activity=page.getByLabel('Current activity', {exact:true});
  await expect(activity.getByRole('textbox',{name:'Answer question 1'})).toBeVisible();
  expect(reads).toBe(1); // The freshly authorized payload is not fetched twice.
  await activity.getByRole('textbox',{name:'Answer question 1'}).fill('Change of velocity over time.');
  await expect(activity).toContainText('Ready while Mentra continues');
  await page.route('**/api/v1/assessments/chat-drafts/early-draft/publish',route=>route.fulfill({status:503,json:{error:{code:'UNAVAILABLE',message:'Please try again.'}}}));
  await activity.getByRole('button',{name:'Add to assessments',exact:true}).click();
  await activity.getByRole('button',{name:'Refresh',exact:true}).click();
  await expect.poll(()=>reads).toBe(2);
  await expect(activity.getByRole('textbox',{name:'Answer question 1'})).toHaveValue('Change of velocity over time.');
  await page.route('**/api/v1/conversations/polish-chat/status*',route=>route.fulfill({json:{
    conversation:{id:'polish-chat',title:'Practice',revision:3,message_count:40,selection:{mode:'STANDARD'},created_at:created,updated_at:created},
    items:[{id:'early-request',conversation_id:'polish-chat',sequence:39,role:'user',content:'Give me one question',created_at:created},
      {id:'early-final',conversation_id:'polish-chat',sequence:40,role:'assistant',content:card.assessment.title,created_at:created,assessment_cards:[card]}],
    turn:{id:'polish-turn',state:'SUCCEEDED',attempt:1,user_sequence:39,selection:{mode:'STANDARD'}},has_more:false,next_cursor:null}}));
  await expect(activity).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Chat assessment'}).getByRole('textbox',{name:'Answer question 1'})).toHaveValue('Change of velocity over time.');
});

test('an early saved assessment retains its conversation actions', async ({ page }) => {
  await workspace(page,true);
  const assessment={id:'early-saved',context_id:'context-1',title:'Saved early practice',purpose:'practice',revision:1,
    created_at:'2026-10-26T00:00:00Z',preferences:{delivery:'interactive'},paper:null,sources:[],questions:[
      {id:'q',question_type:'short_answer',answer_mode:'text',prompt:'What is force?',concept_ids:['force'],difficulty:.3,marks:1,source_tokens:[],options:[]}]};
  let reads=0;
  await page.route('**/api/v1/assessments/early-saved',route=>{reads++;return route.fulfill({json:assessment});});
  await page.route('**/api/v1/conversations/polish-chat/turns/polish-turn/events*',route=>route.fulfill({contentType:'text/event-stream',body:
    `event: activity\ndata: ${JSON.stringify({schema_version:1,conversation_id:'polish-chat',turn_id:'polish-turn',attempt:1,sequence:1,
      step_id:'assessment-result',status:'completed',tool_name:'assessment_generate',user_message:'Practice ready',
      assessment_card:{kind:'saved',id:assessment.id,title:assessment.title}})}\n\n`}));
  await page.goto('/chat/polish-chat');
  const activity=page.getByLabel('Current activity',{exact:true});
  await expect(activity.getByRole('textbox',{name:'Answer question 1'})).toBeVisible();
  await activity.getByText('Practice options',{exact:true}).click();
  await expect(activity.getByRole('button',{name:'Make harder',exact:true})).toBeDisabled();
  expect(reads).toBe(1);
});

test('profile saves apply immediately and tab focus refreshes without BroadcastChannel or login', async ({ page }) => {
  await page.addInitScript(()=>{Object.defineProperty(window,'BroadcastChannel',{configurable:true,value:class {constructor(){throw new Error('Blocked');}}});});
  await workspace(page);
  const profile={learner_id:'polish-user',details:{education_level:'college',field_of_study:'Physics',learning_goal:'Understand motion',learning_preference:'balanced',explanation_depth:'standard',preferred_name:'Ada'},
    estimates:Object.fromEntries(['overall_proficiency','reasoning','quantitative','comprehension','domain_familiarity'].map(key=>[key,{value:null,confidence:0,evidence_count:0}])),
    onboarding_phase:'complete',calibration_status:'skipped',evaluation_status:'not_started',version:1,context_version:1};
  let reads=0, logins=0;
  page.on('request',request=>{if(/\/auth\/(?:login|logout)$/.test(request.url()))logins++;});
  await page.route('**/api/v1/student-profile',route=>{reads++;return route.fulfill({json:profile});});
  await page.route('**/api/v1/student-profile/details',route=>{
    const body=route.request().postDataJSON();
    if (body.expected_version !== profile.version) return route.fulfill({status:409,json:{error:{code:'profile_conflict',message:'Profile changed elsewhere'}}});
    profile.details=body.details;profile.version++;return route.fulfill({json:profile});
  });
  await page.goto('/settings');
  await page.getByRole('button',{name:'Edit profile',exact:true}).click();
  await page.getByLabel('What should Mentra call you?',{exact:true}).fill('Updated immediately');
  await chooseOption(page.getByLabel('Explanation detail',{exact:true}), 'brief');
  await page.getByRole('button',{name:'Save profile',exact:true}).click();
  await expect(page.getByText('Updated immediately',{exact:true})).toBeVisible();
  await expect(page.getByText('Brief',{exact:true})).toBeVisible();
  const before=reads;
  profile.details.preferred_name='Changed in another tab';profile.version++;
  await page.waitForTimeout(550);
  await page.evaluate(()=>{window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'));});
  await expect(page.getByText('Changed in another tab',{exact:true})).toBeVisible();
  expect(reads-before).toBe(1);
  await page.getByRole('button',{name:'Edit profile',exact:true}).click();
  await page.getByLabel('What should Mentra call you?',{exact:true}).fill('Unsaved local draft');
  profile.details.preferred_name='Newer remote change';profile.version++;
  await page.waitForTimeout(550);
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect.poll(()=>reads).toBe(before+2);
  await expect(page.getByLabel('What should Mentra call you?',{exact:true})).toHaveValue('Unsaved local draft');
  await page.getByRole('button',{name:'Save profile',exact:true}).click();
  await expect(page.getByRole('button',{name:'Reload latest profile',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Save profile',exact:true})).toBeDisabled();
  await expect(page.getByLabel('What should Mentra call you?',{exact:true})).toHaveValue('Unsaved local draft');
  await page.getByRole('button',{name:'Reload latest profile',exact:true}).click();
  await expect(page.getByLabel('What should Mentra call you?',{exact:true})).toHaveValue('Newer remote change');
  expect(logins).toBe(0);
});
