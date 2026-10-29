import { test, expect, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import type { Assessment, ChatAssessmentCardData, GenerationJob } from '../src/types/assessments';
import type { AssessmentAttempt } from '../src/types/assessments';

const created = '2026-10-14T00:00:00Z';
function assessment(paper = false): Assessment {
  const questions = [
    { id:'q1', question_type:'mcq', answer_mode:'single_choice' as const, prompt:'Which expression represents force?', options:[{id:'a',label:'Mass × acceleration'},{id:'b',label:'Mass + acceleration'}] },
    { id:'q2', question_type:'true_false', answer_mode:'single_choice' as const, prompt:'A net force changes velocity.', options:[{id:'true',label:'True'},{id:'false',label:'False'}] },
    { id:'q3', question_type:'short_answer', answer_mode:'text' as const, prompt:'Explain inertia in your own words.', options:[] },
    { id:'q4', question_type:'multiple_select', answer_mode:'multiple_choice' as const, prompt:'Select the vector quantities.', options:[{id:'a',label:'Velocity'},{id:'b',label:'Force'},{id:'c',label:'Mass'}] },
  ].map((q,i) => ({...q, concept_ids:['concept'], source_tokens:[], marks:2, difficulty:.4,
    learning_targets: [{topic_id:'topic-arabic',topic_name:'Arabic for beginners',subskill_id:'letter-dots',subskill_name:'Letter dots'},
      {topic_id:'topic-arabic',topic_name:'Arabic for beginners',subskill_id:'letter-shapes',subskill_name:'Letter shapes'}],
    ...(paper ? {number:i<2 ? 1 : 3, part:i===0 ? 'a.i' : i===1 ? 'a.ii' : i===2 ? 'b' : 'c', section:'Section A · Mechanics', context:'A cart moves along a level track. Use this scenario for the following parts.'} : {})}));
  return { id:'flex-assessment', context_id:'context-1', title:'Motion and reasoning', purpose:'practice', revision:1, created_at:created, sources:[], questions,
    paper: paper ? { duration_minutes:90,total_marks:8,question_count:2,instructions:'Answer all parts. Show your working.',sections:[{title:'Section A · Mechanics',question_count:2,question_type:'written',part_marks:[2,2]}] } : null };
}

async function chat(page: Page, paper = false, generation = false) {
  await workspace(page, false, true);
  const value = assessment(paper);
  const card: ChatAssessmentCardData = {id:'flex-draft',assessment_id:value.id,conversation_id:'polish-chat',assessment:value};
  let attempt: Record<string, unknown> | null = null;
  const submissions: Record<string, unknown>[] = [];
  const retries: Record<string, unknown>[] = [];
  let starts=0;
  const job: GenerationJob = {id:'flex-job',state:'running',title:value.title,completed_parts:1,total_parts:4,result:null,error:null,can_retry:false};
  await page.route('**/api/v1/conversations/polish-chat/status*', route => route.fulfill({json:{conversation:{id:'polish-chat',title:'Flexible assessment',revision:8,message_count:2,selection:{mode:'STANDARD'},created_at:created,updated_at:created},items:[{id:'request',conversation_id:'polish-chat',sequence:1,role:'user',content:'Practice mechanics.',created_at:created},{id:'reply',conversation_id:'polish-chat',sequence:2,role:'assistant',content:'Your practice session.',created_at:created,assessment_cards:[generation ? {id:job.id,generation_job_id:job.id,title:value.title} : card]}],turn:{id:'turn',state:'SUCCEEDED',attempt:1,user_sequence:1,selection:{mode:'STANDARD'}},has_more:false,next_cursor:null}}));
  await page.route('**/api/v1/assessments/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith('/chat-drafts/flex-draft')) body = card;
    else if (path.endsWith('/generation-jobs/flex-job/retry')) { job.state='running'; job.can_retry=false; job.error=null; body=job; }
    else if (path.endsWith('/generation-jobs/flex-job')) body=job;
    else if (path.endsWith('/flex-assessment/attempts') && route.request().method()==='POST') {
      starts++;
      attempt={id:'flex-attempt',assessment_id:value.id,revision:1,state:'draft',attempt_number:1,answers:{},grades:null,extraction:null,error:null,evidence_status:'none',created_at:created,grade_revision:1,grade_history:[]}; body=attempt;
    } else if (path.endsWith('/flex-assessment/attempts')) body=attempt ? [attempt] : [];
    else if (path.endsWith('/flex-attempt/retry')) {
      retries.push(route.request().postDataJSON()); attempt={...attempt,state:'submitted',revision:Number(attempt?.revision)+1,error:null,retry_pending:false}; body=attempt;
    }
    else if (path.endsWith('/flex-attempt/draft')) {
      const payload=route.request().postDataJSON(); attempt={...attempt,answers:payload.answers,revision:2}; body=attempt;
    }
    else if (path.endsWith('/flex-attempt/submission')) {
      const payload=route.request().postDataJSON(); submissions.push(payload);
      attempt={...attempt,answers:payload.answers,state:'submitted',revision:2}; body=attempt;
    } else if (path.endsWith('/attempts/flex-attempt')) body=attempt;
    else if (path.endsWith('/flex-assessment')) body=value;
    else if (path.endsWith('/preferences')) body={auto_add:false,revision:1};
    await route.fulfill({json:body});
  });
  await page.goto('/chat/polish-chat');
  return {value,card,job,submissions,retries,starts:()=>starts,setAttempt:(value:Record<string,unknown>)=>{attempt=value;}};
}

for (const width of [390,1280]) test(`mixed interactive practice keeps typed and multiple-choice answers at ${width}`, async ({page},info) => {
  await page.setViewportSize({width,height:844}); const state=await chat(page);
  const quiz=page.getByRole('region',{name:'Interactive quiz'});
  const skills=quiz.getByRole('list',{name:'Skills practised'});
  await expect(skills.getByText('Arabic for beginners',{exact:true})).toHaveCount(1);
  await expect(skills.getByText('Letter dots',{exact:true})).toBeVisible();
  await expect(skills.getByText('Letter shapes',{exact:true})).toBeVisible();
  await quiz.getByRole('radio',{name:'Mass × acceleration',exact:true}).check();
  await quiz.getByRole('button',{name:'Next',exact:true}).click();
  await expect(quiz.getByText('True or false',{exact:true})).toBeVisible();
  await quiz.getByRole('radio',{name:'True',exact:true}).check();
  await quiz.getByRole('button',{name:'Next',exact:true}).click();
  await quiz.getByLabel('Answer question 3').fill('   ');
  await expect(quiz.getByRole('button',{name:'Next',exact:true})).toBeDisabled();
  await quiz.getByLabel('Answer question 3').fill('Inertia resists a change in velocity.');
  await quiz.getByRole('button',{name:'Next',exact:true}).click();
  await quiz.getByRole('checkbox',{name:'Velocity',exact:true}).check(); await quiz.getByRole('checkbox',{name:'Force',exact:true}).check();
  await quiz.getByRole('button',{name:'Go to question 3, answered'}).click();
  await expect(quiz.getByLabel('Answer question 3')).toHaveValue('Inertia resists a change in velocity.');
  await quiz.getByRole('button',{name:'Go to question 4, answered'}).click();
  await expect(quiz.getByRole('checkbox',{name:'Velocity',exact:true})).toBeChecked();
  expect(state.submissions).toHaveLength(0);
  await page.screenshot({path:info.outputPath(`mixed-practice-${width}.png`)});
  await quiz.getByRole('button',{name:'Submit',exact:true}).click();
  await expect.poll(() => state.submissions.length).toBe(1);
  expect(state.submissions[0].answers).toEqual({q1:'a',q2:'true',q3:'Inertia resists a change in velocity.',q4:'["a","b"]'});
  expect(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('mock paper retains nested question references, marks and shared context', async ({page},info) => {
  await page.setViewportSize({width:390,height:844}); await chat(page,true);
  const paper=page.getByLabel('Exam paper');
  await expect(paper.getByText('90 minutes')).toBeVisible();
  await expect(paper.getByText('2 questions · 8 marks').first()).toBeVisible();
  await expect(paper.getByRole('heading',{name:'Question 1 (a) (ii)',exact:true})).toBeVisible();
  await page.evaluate(() => {
    new MutationObserver(() => {
      const frame=document.querySelector<HTMLIFrameElement>('iframe[title="Printable assessment"]');
      if (frame?.contentWindow) frame.contentWindow.print=() => { (window as unknown as {printedPaper:string}).printedPaper=frame.contentDocument!.body.innerHTML; };
    }).observe(document.body,{childList:true});
  });
  await paper.getByRole('button',{name:'Print paper',exact:true}).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as {printedPaper:string}).printedPaper ?? ''),{timeout:12000}).toContain('Question 1 (a) (ii)');
  const printed=await page.evaluate(() => (window as unknown as {printedPaper:string}).printedPaper);
  expect(printed).toContain('90 minutes'); expect(printed).not.toContain('correct_option'); expect(printed).not.toContain('Practice mechanics.');
  await page.screenshot({path:info.outputPath('mock-paper-mobile.png'),fullPage:true});
  await page.reload(); await expect(page.getByLabel('Exam paper').getByText('90 minutes')).toBeVisible();
  await page.getByRole('button',{name:'Answer in UI',exact:true}).click();
  const sheet=page.getByRole('region',{name:'Assessment answer sheet'});
  await sheet.getByLabel('Answer 3 (b)',{exact:true}).fill('A saved written explanation.');
  await sheet.getByRole('button',{name:'Save progress',exact:true}).click();
  await expect(sheet.getByRole('button',{name:'Save progress',exact:true})).toBeEnabled();
  await page.reload();
  await expect(page.getByLabel('Answer 3 (b)',{exact:true})).toHaveValue('A saved written explanation.');
});

test('generation progress survives reload and replaces itself with the completed assessment', async ({page}) => {
  const state=await chat(page,true,true);
  const progress=page.getByRole('region',{name:'Assessment generation'});
  await expect(progress).toContainText('1 of 4');
  await page.reload(); await expect(progress).toContainText('1 of 4');
  state.job.state='completed'; state.job.completed_parts=4; state.job.result=state.card;
  await expect(page.getByLabel('Exam paper')).toBeVisible();
  await expect(progress).toHaveCount(0);
});

test('creation needs only a topic and automatically decides advanced settings', async ({page}) => {
  await workspace(page,false,true);
  let payload: Record<string,unknown> | undefined;
  await page.route('**/api/v1/assessments/generation-jobs', async route => {
    payload=route.request().postDataJSON();
    await route.fulfill({json:{id:'auto-job',state:'queued',title:'Your assessment',completed_parts:0,total_parts:null,result:null,error:null,can_retry:false}});
  });
  await page.route('**/api/v1/assessments/generation-jobs/auto-job', route => route.fulfill({json:{id:'auto-job',state:'queued',title:'Your assessment',completed_parts:0,total_parts:null,result:null,error:null,can_retry:false}}));
  await page.goto('/assessments?tab=create');
  const form=page.getByRole('form',{name:'Create assessment'});
  await expect(form).toBeVisible();
  await form.getByLabel('Topic', {exact:true}).fill('Forces');
  await expect(form.getByLabel('Assessment learning context')).toHaveCount(0);
  await expect(form.getByLabel('Assessment level')).toHaveCount(0);
  await form.getByRole('button',{name:'Generate assessment',exact:true}).click();
  await expect(page.getByRole('region',{name:'Assessment generation'})).toBeVisible();
  expect(payload).toMatchObject({topic:'Forces',context_id:'',count:5,question_format:'auto'});
});

for (const width of [390,1280]) test(`completed assessment groups repeated topic and skill labels at ${width}`, async ({page}) => {
  await page.setViewportSize({width,height:844});
  const state=await chat(page);
  const attempt: AssessmentAttempt={id:'flex-attempt',assessment_id:state.value.id,revision:3,state:'graded',attempt_number:1,
    answers:Object.fromEntries(state.value.questions.map(q=>[q.id,q.options?.[0]?.id ?? 'My explanation'])),
    grades:state.value.questions.map(q=>({question_id:q.id,score:2,confidence:1,feedback:'Correct.',concept_grades:{},misconceptions:[],outcome:'correct'})),
    extraction:null,error:null,evidence_status:'applied',created_at:created,grade_revision:1,grade_history:[]};
  await page.route('**/api/v1/assessments/flex-assessment/attempts',route=>route.fulfill({json:[attempt]}));
  await page.route('**/api/v1/assessments/attempts/flex-attempt',route=>route.fulfill({json:attempt}));
  await page.reload();
  const coverage=page.getByRole('region',{name:'Topics covered',exact:true});
  await expect(coverage.getByText('Arabic for beginners',{exact:true})).toHaveCount(1);
  await expect(coverage.getByText('Letter dots',{exact:true})).toHaveCount(1);
  await expect(coverage.getByText('Letter shapes',{exact:true})).toHaveCount(1);
  await expect(page.getByText('Final result: 8/8',{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('simple grading shows correctness and feedback without marks or letter grades', async ({page}) => {
  const state=await chat(page);
  state.value.preferences={result_style:'grade'};
  await page.reload();
  await expect(page.getByRole('region',{name:'Interactive quiz'})).not.toContainText(/\bmarks?\b/);
  const attempt: AssessmentAttempt={id:'flex-attempt',assessment_id:state.value.id,revision:3,state:'graded',attempt_number:1,
    answers:Object.fromEntries(state.value.questions.map(q=>[q.id,q.options?.[0]?.id ?? 'My explanation'])),
    grades:state.value.questions.map(q=>({question_id:q.id,score:2,confidence:1,feedback:'Your reasoning is accurate.',concept_grades:{},misconceptions:[],outcome:'correct'})),
    extraction:null,error:null,evidence_status:'applied',created_at:created,grade_revision:1,grade_history:[]};
  await page.route('**/api/v1/assessments/flex-assessment/attempts',route=>route.fulfill({json:[attempt]}));
  await page.route('**/api/v1/assessments/attempts/flex-attempt',route=>route.fulfill({json:attempt}));
  await page.reload();
  const feedback=page.getByRole('region',{name:'Assessment feedback'});
  await expect(feedback).toBeVisible();
  await expect(feedback.getByText('Your reasoning is accurate.')).toHaveCount(4);
  await feedback.getByRole('button',{name:'List view',exact:true}).click();
  await expect(feedback.getByText('Your reasoning is accurate.')).toHaveCount(4);
  await expect(feedback).not.toContainText(/marks|8\/8|2\/2|Practice grade|A ≥/i);
});

test('retry evaluation preserves the same submitted attempt and answers', async ({page}) => {
  const state=await chat(page);
  const answers={q1:'a',q2:'true',q3:'Inertia resists change in motion.',q4:'["a","b"]'};
  state.setAttempt({id:'flex-attempt',assessment_id:state.value.id,revision:3,state:'failed',attempt_number:1,
    answers,grades:null,extraction:null,error:'Grading is temporarily unavailable.',retry_pending:false,
    evidence_status:'pending',created_at:created,grade_revision:1,grade_history:[]});
  await page.reload();
  await expect(page.getByRole('button',{name:'Retry evaluation',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Start new attempt',exact:true})).toHaveCount(0);
  await expect(page.getByRole('group',{name:'Your answer'}).filter({hasText:'Inertia resists change in motion.'})).toBeVisible();
  await page.getByRole('button',{name:'Retry evaluation',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Evaluating your answers'})).toBeVisible();
  expect(state.retries).toHaveLength(1);
  expect(state.retries[0]).toMatchObject({expected_revision:3});
  expect(state.starts()).toBe(0);
  expect(state.submissions).toHaveLength(0);
  await expect(page.getByRole('group',{name:'Your answer'}).filter({hasText:'Inertia resists change in motion.'})).toBeVisible();
});

test('results use compact two-column grids with full review and list views', async ({page},info) => {
  await page.setViewportSize({width:390,height:844});
  const state=await chat(page);
  state.value.questions.forEach(question => { question.prompt += ' A long explanation that must stay within the compact preview.'.repeat(50); });
  state.setAttempt({id:'flex-attempt',assessment_id:state.value.id,revision:3,state:'graded',attempt_number:1,
    answers:{q1:'a',q2:'false',q3:'An incomplete explanation',q4:'["a","b"]'},
    grades:state.value.questions.map((q,i)=>({question_id:q.id,score:i===1?0:i===2?1:2,confidence:1,
      feedback:`Feedback for question ${i+1}`,concept_grades:{},misconceptions:[],outcome:i===1?'wrong':i===2?'partial':'correct'})),
    extraction:null,error:null,evidence_status:'applied',created_at:created,grade_revision:1,grade_history:[]});
  await page.reload();
  const feedback=page.getByRole('region',{name:'Assessment feedback'});
  const cards=feedback.locator('.workspace-compact-grid > article');
  await expect(cards).toHaveCount(4);
  const boxes=await cards.evaluateAll(items=>items.map(item=>({x:item.getBoundingClientRect().x,y:item.getBoundingClientRect().y,height:item.getBoundingClientRect().height})));
  expect(boxes[0].y).toBe(boxes[1].y); expect(boxes[1].x).toBeGreaterThan(boxes[0].x);
  expect(boxes.every(box=>box.height===224)).toBe(true);
  expect(await cards.first().locator('p').first().evaluate(element => getComputedStyle(element).marginTop)).toBe('0px');
  await cards.nth(1).getByRole('button',{name:'Review result'}).click();
  const dialog=page.getByRole('dialog');
  const wrong=dialog.getByRole('region',{name:'Question 2 feedback',exact:true});
  await expect(wrong).toHaveClass(/bg-danger/);
  await expect(wrong.getByRole('group',{name:'Your answer'})).toContainText('False');
  await dialog.getByRole('button',{name:'Next result',exact:true}).click();
  await expect(dialog.getByRole('region',{name:'Question 3 feedback',exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await feedback.getByRole('button',{name:'List view',exact:true}).click();
  await expect(feedback.getByRole('group',{name:'Your answer'})).toHaveCount(4);
  await feedback.getByRole('button',{name:'Grid view',exact:true}).click();
  await expect(cards).toHaveCount(4);
  await page.screenshot({path:info.outputPath('assessment-results-mobile.png')});
});

test('question transitions follow button and numbered navigation while preserving answers', async ({page}) => {
  await page.emulateMedia({reducedMotion:'no-preference'});
  await chat(page);
  const quiz=page.getByRole('region',{name:'Interactive quiz'});
  const card=quiz.locator('.question-transition');
  await expect(card).toHaveAttribute('data-navigation','none');
  await quiz.getByRole('radio',{name:'Mass × acceleration',exact:true}).check();
  await quiz.getByRole('button',{name:'Next',exact:true}).click();
  await expect(card).toHaveAttribute('data-navigation','forward');
  await expect(card).toHaveCSS('animation-name','question-forward');
  await quiz.getByRole('button',{name:'Go to question 3',exact:true}).click();
  await quiz.getByLabel('Answer question 3').fill('My preserved answer');
  await quiz.getByRole('button',{name:'Back',exact:true}).click();
  await expect(card).toHaveAttribute('data-navigation','backward');
  await expect(card).toHaveCSS('animation-name','question-backward');
  await quiz.getByRole('button',{name:'Go to question 3, answered',exact:true}).click();
  await expect(quiz.getByLabel('Answer question 3')).toHaveValue('My preserved answer');
  await page.emulateMedia({reducedMotion:'reduce'});
  await quiz.getByRole('button',{name:'Back',exact:true}).click();
  await expect(card).toHaveCSS('animation-name','none');
});

test('results remain usable while learning updates run in the background', async ({page}) => {
  const state=await chat(page);
  const attempt={id:'flex-attempt',assessment_id:state.value.id,revision:3,state:'graded',attempt_number:1,
    answers:{q1:'a',q2:'true',q3:'An explanation',q4:'["a","b"]'},
    grades:state.value.questions.map(q=>({question_id:q.id,score:2,confidence:1,feedback:'Correct reasoning.',concept_grades:{},misconceptions:[],outcome:'correct'})),
    extraction:null,error:null,evidence_status:'pending',created_at:created,grade_revision:1,grade_history:[]};
  state.setAttempt(attempt);
  await page.reload();
  const feedback=page.getByRole('region',{name:'Assessment feedback'});
  await expect(feedback).toBeVisible();
  await expect(page.getByText('Results saved. Learning progress updates in the background.',{exact:true})).toBeVisible();
  await expect(page.getByText('Evaluating your answers…',{exact:true})).toHaveCount(0);
  await feedback.getByRole('button',{name:'Review result',exact:true}).first().click();
  await page.getByRole('dialog').getByRole('button',{name:'Next result',exact:true}).click();
  await expect(page.getByRole('dialog').getByRole('region',{name:'Question 2 feedback',exact:true})).toBeVisible();
  state.setAttempt({...attempt,evidence_status:'applied',revision:4});
  await expect(page.getByText('Feedback saved and learning progress updated.',{exact:true})).toBeVisible({timeout:15000});
  await expect(page.getByRole('dialog').getByRole('region',{name:'Question 2 feedback',exact:true})).toBeVisible();
});
