import { test, expect, type Page } from '@playwright/test';

async function workspace(page: Page, failFirst = false, loseReply = false, codeAnswers = false) {
  const date = '2026-10-12T00:00:00Z';
  const selection = { mode:'STANDARD' };
  const conversation = { id:'quiz-chat', title:'Local quiz chat', revision:3, message_count:2, selection, created_at:date, updated_at:date, deleted_at:null };
  const assessment = { id:'assessment-quiz', context_id:'context-quiz', title:'Code quiz', purpose:'practice', revision:1, sources:[], created_at:date,
    questions:Array.from({length:3}, (_, index) => ({id:`question-${index+1}`, prompt:`What does this code print?\n\n\`\`\`python\nvalue = ${index+1}\nprint(value + 1)\n\`\`\``, concept_ids:['concept-1'], marks:2, difficulty:.3, source_tokens:[], options:[{id:'a',label:codeAnswers ? '```python\nprint(2)\n```' : 'A supported explanation.'},{id:'b',label:'An unsupported explanation.'}]})) };
  const card = { id:'draft-quiz', conversation_id:conversation.id, assessment_id:assessment.id, assessment };
  const items = [{id:'question',conversation_id:conversation.id,sequence:1,role:'user',content:'Give me a code quiz.',created_at:date},
    {id:'reply',conversation_id:conversation.id,sequence:2,role:'assistant',content:'Your quiz is ready.',assessment_cards:[card],created_at:date}];
  let attempt: Record<string, any> | null = null, starts = 0, signedIn = true;
  const submissions: Record<string, any>[] = [], writes: string[] = [];
  let release!: () => void;
  let hold: Promise<void> | null = null;
  let entered!: () => void;
  let requested: Promise<void> = Promise.resolve();
  const identity = { learner_id:'quiz-user', username:'quiz-user', user_id:null, provider:null };
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') writes.push(path);
    let body: unknown = [];
    if (path.endsWith('/auth/me')) {
      if (!signedIn) return route.fulfill({status:401,json:{error:{code:'AUTH_REQUIRED',message:'Sign in.'}}});
      body = identity;
    } else if (path.endsWith('/auth/logout')) { signedIn = false; return route.fulfill({status:204}); }
    else if (path.endsWith('/auth/login')) { signedIn = true; body = identity; }
    else if (path.endsWith('/student-profile')) body = {learner_id:identity.learner_id,details:{education_level:'college',field_of_study:'Programming',learning_goal:'Learn',learning_preference:'balanced',explanation_depth:'standard'},estimates:Object.fromEntries(['overall_proficiency','reasoning','quantitative','comprehension','domain_familiarity'].map(key => [key,{value:null,confidence:0,evidence_count:0}])),onboarding_phase:'complete',calibration_status:'skipped',evaluation_status:'not_started',version:1,context_version:1};
    else if (path.endsWith('/conversations/sync')) body = {reset:false,cursor:3,has_more:false,conversations:[conversation],deleted_ids:[],list_cursor:null};
    else if (path.endsWith('/status')) body = {conversation,items,has_more:false,next_cursor:null,turn:{id:'quiz-turn',state:'SUCCEEDED',attempt:1,user_sequence:1,selection,error:null}};
    else if (path.endsWith('/chat-drafts/draft-quiz')) body = card;
    else if (path.endsWith('/assessment-quiz/attempts') && request.method() === 'POST') {
      starts++;
      attempt = {id:'attempt-quiz',assessment_id:assessment.id,revision:1,state:'draft',attempt_number:1,answers:{},grades:null,extraction:null,error:null,evidence_status:'none',created_at:date,grade_revision:1,grade_history:[]}; body = attempt;
    } else if (path.endsWith('/assessment-quiz/attempts')) body = attempt ? [attempt] : [];
    else if (path.endsWith('/attempt-quiz/submission')) {
      const payload = request.postDataJSON(); submissions.push(payload); entered?.();
      if (hold) await hold;
      if (failFirst && submissions.length === 1) return route.fulfill({status:503,json:{error:{code:'SERVICE_UNAVAILABLE',message:'Try again.'}}});
      attempt = {...attempt!,revision:2,state:'submitted',answers:payload.answers,evidence_status:'pending'};
      if (loseReply && submissions.length === 1) return route.abort('failed');
      body = attempt;
    } else if (path.endsWith('/attempts/attempt-quiz')) body = attempt;
    else if (path.endsWith('/notifications/unread-count')) body = {count:0};
    else if (path.endsWith('/assessments/preferences')) body = {auto_add:false,revision:1};
    await route.fulfill({json:body});
  });
  await page.goto('/chat/quiz-chat');
  const quiz = page.getByRole('region',{name:'Interactive quiz'});
  await expect(quiz.getByText(/Question 1 of 3/)).toBeVisible();
  return {assessment,quiz,writes,submissions,starts:() => starts,attempt:() => attempt,
    hold() { hold = new Promise<void>(resolve => {release=resolve;}); requested = new Promise<void>(resolve => {entered=resolve;}); },
    requested:() => requested, release:() => {release();hold=null;},
    grade() { attempt = {...attempt!,revision:3,state:'graded',evidence_status:'applied',grades:assessment.questions.map(q => ({question_id:q.id,score:2,confidence:1,feedback:codeAnswers ? 'Correct.\n\n```python\nprint(2)\n```' : 'Correct.',concept_grades:{},misconceptions:[],outcome:'correct',correct_answer:'A supported explanation.'}))}; },
  };
}

async function answerAll(page: Page) {
  const quiz = page.getByRole('region',{name:'Interactive quiz'});
  for (let i=1;i<=3;i++) {
    await quiz.getByRole('radio',{name:'A supported explanation.',exact:true}).check();
    if (i<3) await quiz.getByRole('button',{name:'Next',exact:true}).click();
  }
}

test('Next is local, code uses shared blocks, and navigation preserves choices without database writes', async ({page}) => {
  const state = await workspace(page);
  await expect(state.quiz.locator('.code-block[data-language="python"]')).toBeVisible();
  await expect(state.quiz.getByRole('button',{name:'Copy code',exact:true})).toBeVisible();
  await state.quiz.getByRole('radio').first().check();
  await state.quiz.getByRole('button',{name:'Next',exact:true}).click();
  await expect(state.quiz.getByText(/Question 2 of 3/)).toBeVisible();
  expect(state.starts()).toBe(0); expect(state.writes).toEqual([]);
  await page.getByRole('button',{name:'Start a new chat'}).click();
  await page.getByRole('link',{name:'Local quiz chat',exact:true}).click();
  await expect(state.quiz.getByText(/Question 2 of 3/)).toBeVisible();
  await state.quiz.getByRole('button',{name:'Back',exact:true}).click();
  await expect(state.quiz.getByRole('radio').first()).toBeChecked();
  expect(state.starts()).toBe(0);
  await page.reload();
  await expect(state.quiz.getByText(/Question 1 of 3/)).toBeVisible();
  await expect(state.quiz.getByRole('radio').first()).not.toBeChecked();
});

test('one final Submit sends all answers and shows review plus a visible composer evaluation indicator', async ({page}) => {
  const state = await workspace(page); await answerAll(page);
  await expect(state.quiz.getByRole('button',{name:'Finish quiz'})).toHaveCount(0);
  await expect(state.quiz.getByRole('button',{name:'Save answer'})).toHaveCount(0);
  expect(state.writes).toEqual([]);
  state.hold();
  await state.quiz.getByRole('button',{name:'Submit',exact:true}).click(); await state.requested();
  try {
    await expect(page.getByRole('region',{name:'Quiz answers'}).getByRole('heading',{name:/Question/})).toHaveCount(3);
    const indicator = page.getByRole('form',{name:'Message Mentra'}).getByRole('status',{name:'Quiz evaluation'});
    await expect(indicator).toContainText('Submitting quiz answers'); await expect(indicator).toBeInViewport();
  } finally {state.release();}
  await expect(page.getByRole('form',{name:'Message Mentra'}).getByRole('status',{name:'Quiz evaluation'})).toContainText('Evaluating quiz answers');
  await expect(page.getByRole('region',{name:'Quiz answers'}).getByRole('heading',{name:/Question/})).toHaveCount(3);
  expect(state.starts()).toBe(1); expect(state.submissions).toHaveLength(1);
  expect(state.submissions[0].answers).toEqual({'question-1':'a','question-2':'a','question-3':'a'});
  expect(state.writes.some(path => path.endsWith('/draft'))).toBe(false);
  await page.getByRole('button',{name:'Start a new chat'}).click();
  await expect(page.getByRole('status',{name:'Quiz evaluation'})).toContainText('Evaluating quiz answers');
  state.grade();
  await expect(page.getByRole('status',{name:'Quiz evaluation'})).toHaveCount(0,{timeout:10_000});
  await page.getByRole('link',{name:'Local quiz chat',exact:true}).click();
  await expect(page.getByText('Final result: 6/6',{exact:true})).toBeVisible();
});

test('failed final submissions keep choices and retry the same payload without starting another attempt', async ({page}) => {
  const state = await workspace(page, true); await answerAll(page);
  await state.quiz.getByRole('button',{name:'Submit',exact:true}).click();
  await expect(state.quiz.getByRole('alert')).toBeVisible();
  await expect(state.quiz.getByRole('radio').first()).toBeChecked();
  await expect(page.getByRole('status',{name:'Quiz evaluation'})).toHaveCount(0);
  await state.quiz.getByRole('button',{name:'Submit',exact:true}).click();
  await expect(page.getByRole('region',{name:'Quiz answers'})).toBeVisible();
  expect(state.starts()).toBe(1); expect(state.submissions).toHaveLength(2);
  expect(state.submissions[0]).toEqual(state.submissions[1]);
});

test('a lost submission reply recovers saved answers and continues evaluation', async ({page}) => {
  const state = await workspace(page, false, true); await answerAll(page);
  await state.quiz.getByRole('button',{name:'Submit',exact:true}).click();
  await expect(page.getByRole('region',{name:'Quiz answers'})).toBeVisible();
  await expect(page.getByRole('status',{name:'Quiz evaluation'})).toContainText('Evaluating quiz answers');
  expect(state.submissions).toHaveLength(1); expect(state.starts()).toBe(1);
  state.grade();
  await expect(page.getByText('Final result: 6/6',{exact:true})).toBeVisible({timeout:10_000});
});

test('logout clears unsent quiz choices from session memory', async ({page}) => {
  const state = await workspace(page);
  await state.quiz.getByRole('radio').first().check();
  await state.quiz.getByRole('button',{name:'Next',exact:true}).click();
  await page.getByRole('button',{name:/Account menu/}).click();
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('Username',{exact:true}).fill('quiz-user');
  await page.getByLabel('Password',{exact:true}).fill('test password');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('link',{name:'Local quiz chat',exact:true}).click();
  await expect(state.quiz.getByText(/Question 1 of 3/)).toBeVisible();
  await expect(state.quiz.getByRole('radio').first()).not.toBeChecked();
});

test('completed quiz actions share a compact wrapping footer', async ({page}, testInfo) => {
  const state = await workspace(page); await answerAll(page);
  await state.quiz.getByRole('button',{name:'Submit',exact:true}).click();
  await expect(page.getByRole('region',{name:'Quiz answers'})).toBeVisible();
  state.grade();
  const correction = page.getByRole('button',{name:'Correct answers or transcription',exact:true});
  await expect(correction).toBeVisible({timeout:10_000});
  const footer = correction.locator('..');
  await expect(footer.getByRole('button')).toHaveCount(3);
  await expect(footer.getByRole('button',{name:'Try again',exact:true})).toBeVisible();
  const view = footer.getByRole('button',{name:'View in assessments',exact:true});
  await expect(view).toBeVisible();
  const desktop = await footer.getByRole('button').evaluateAll(elements => elements.map(element => ({top:element.getBoundingClientRect().top,height:element.getBoundingClientRect().height})));
  expect(new Set(desktop.map(value => value.top)).size).toBe(1);
  expect(desktop.every(value => value.height === 36)).toBeTruthy();
  await footer.scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('quiz-footer-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await footer.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  const mobile = await footer.getByRole('button').evaluateAll(elements => elements.map(element => element.getBoundingClientRect().top));
  expect(new Set(mobile).size).toBeGreaterThan(1);
  await page.screenshot({path:testInfo.outputPath('quiz-footer-mobile.png')});
  await view.click();
  await expect(page).toHaveURL(/\/assessments\?assessment=assessment-quiz$/);
});

test('assessment results render question, answer and feedback code through Prism', async ({page}, testInfo) => {
  const state = await workspace(page,false,false,true);
  for(let i=1;i<=3;i++) {
    await state.quiz.getByRole('radio').first().check();
    if(i<3) await state.quiz.getByRole('button',{name:'Next',exact:true}).click();
  }
  await state.quiz.getByRole('button',{name:'Submit',exact:true}).click();
  await expect(page.getByRole('region',{name:'Quiz answers'})).toBeVisible();
  state.grade();
  const result=page.getByRole('region',{name:'Question 1 feedback',exact:true});
  await expect(result).toBeVisible({timeout:10_000});
  await expect(result.locator('.code-block[data-language="python"]')).toHaveCount(3);
  await expect(result.locator('.token.number').first()).toBeVisible();
  await result.scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('compact-code-feedback-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(() => page.getByRole('complementary',{name:'Main navigation'}).evaluate(element => element.getBoundingClientRect().right)).toBeLessThanOrEqual(0);
  await result.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({path:testInfo.outputPath('compact-code-feedback-mobile.png')});
});
