import { test, expect, type Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';
import { chooseOption } from './select-helpers';

const assessment = {
  id:'sheet-assessment', context_id:'context-1', title:'Forces practice', purpose:'practice', revision:1,
  created_at:'2026-10-25T00:00:00Z', sources:[],
  questions:[{id:'q1',number:1,prompt:'Which equation describes force?',answer_mode:'single_choice',question_type:'mcq',options:[{id:'a',label:'Mass times acceleration'},{id:'b',label:'Mass plus acceleration'}],marks:2,concept_ids:[],difficulty:.4,source_tokens:[]},
    {id:'q2',number:2,prompt:'Explain inertia.',answer_mode:'text',question_type:'short_answer',options:[],marks:3,concept_ids:[],difficulty:.4,source_tokens:[]}],
};

async function fixture(page: Page, written = false, failFirst = false) {
  await workspace(page);
  const value = written ? {...assessment, questions:assessment.questions.map(q => ({...q,options:[],answer_mode:'text',question_type:'written'}))} : assessment;
  let attempt: Record<string,unknown> | null = null, sourceReads=0, starts=0, uploads=0;
  let turnId='sheet-turn', userSequence=1;
  const bodies: Record<string,unknown>[] = [];
  const card = {id:null,conversation_id:'polish-chat',assessment_id:value.id,assessment:value};
  const messages: Record<string,unknown>[] = [{id:'question',conversation_id:'polish-chat',sequence:1,role:'user',content:'Create practice.',created_at:value.created_at}, {id:'answer',conversation_id:'polish-chat',sequence:2,role:'assistant',content:'Try these questions.',created_at:value.created_at,assessment_cards:[card]}];
  const snapshot = () => ({conversation:{id:'polish-chat',title:value.title,revision:messages.length,message_count:messages.length,selection:{mode:'STANDARD'},created_at:value.created_at,updated_at:value.created_at},items:messages,turn:{id:turnId,state:'SUCCEEDED',attempt:1,user_sequence:userSequence,selection:{mode:'STANDARD'}},has_more:false,next_cursor:null});
  function begin() {
    starts++; attempt={id:'sheet-attempt',assessment_id:value.id,revision:1,state:'draft',attempt_number:1,answers:{},grades:null,extraction:null,error:null,evidence_status:'none',created_at:value.created_at,grade_revision:1,grade_history:[]};
  }
  function extract() {
    attempt={...attempt,state:'pending_transcription',revision:Number(attempt!.revision)+1,extraction:{answers:{q1:written ? 'Mass times acceleration' : 'a',q2:'Inertia resists changes in motion.'},text:'1. A\n2. Inertia resists changes in motion.',warnings:[],reader_revision:'fixture',handwriting_support:'vision_requires_review'}};
  }
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname, method=route.request().method();
    let body: unknown;
    if (path.endsWith('/conversations/polish-chat/status')) body=snapshot();
    else if (path.endsWith('/conversations/turns')) {
      const request=route.request().postDataJSON(); expect(request.attachment_ids).toEqual(['sheet-attachment']); turnId=request.client_turn_id; userSequence=3;
      begin(); extract();
      messages.push({id:'upload-message',conversation_id:'polish-chat',sequence:3,role:'user',content:request.content,created_at:value.created_at}, {id:'upload-answer',conversation_id:'polish-chat',sequence:4,role:'assistant',content:'Review your extracted answers.',created_at:value.created_at,assessment_cards:[{...card,attempt_id:'sheet-attempt'}]}); body=snapshot();
    } else if (path.endsWith('/files/uploads')) { uploads++; body={id:'sheet-file',filename:'answers.txt',size_bytes:100,media_type:'text/plain',state:'STAGED',purpose:'assessment'}; }
    else if (path.endsWith('/chat-attachments') && method==='POST') body={id:'sheet-attachment',filename:'answers.txt',size_bytes:100};
    else if (path.includes('/chat-attachments/')) body={id:'sheet-attachment',filename:'answers.txt',size_bytes:100,ready:true,warnings:[],error:null,library_result:null};
    else if (path.endsWith('/sheet-assessment/paper.pdf')) return route.fulfill({contentType:'application/pdf',body:Buffer.from('%PDF-1.4\nfixture paper')});
    else if (path.endsWith('/sheet-assessment/attempts') && method==='POST') { begin(); body=attempt; }
    else if (path.endsWith('/sheet-assessment/attempts')) body=attempt ? [attempt] : [];
    else if (path.endsWith('/sheet-assessment')) body=value;
    else if (path.endsWith('/sheet-attempt/draft')) { const request=route.request().postDataJSON(); attempt={...attempt,answers:request.answers,reported_assistance:request.assistance ?? attempt?.reported_assistance,revision:Number(attempt!.revision)+1}; body=attempt; }
    else if (path.endsWith('/sheet-attempt/source')) {
      sourceReads++;
      if (failFirst && sourceReads===1) return route.fulfill({status:503,json:{error:{code:'UNAVAILABLE',message:'Retry'}}});
      extract(); body=attempt;
    } else if (path.endsWith('/sheet-attempt/submission')) {
      const request=route.request().postDataJSON(); bodies.push(request);
      expect(request.transcription_confirmed).toBe(true); expect(request.answers).toMatchObject({q1:written ? 'Mass times acceleration':'a',q2:'Inertia resists changes in motion.'});
      attempt={...attempt,answers:request.answers,reported_assistance:request.assistance ?? 'unknown',state:'submitted',revision:Number(attempt!.revision)+1}; body=attempt;
    } else if (path.endsWith('/attempts/sheet-attempt')) {
      if (attempt?.state==='submitted') attempt={...attempt,state:'graded',revision:Number(attempt.revision)+1,evidence_status:'applied',scoring:{raw_score:3,adjusted_score:attempt.reported_assistance==='assisted' ? 2.7:3,max_score:5,multiplier:attempt.reported_assistance==='assisted' ? .9:1,reported_assistance:attempt.reported_assistance,policy:'self-reported-assistance-v1'},grades:value.questions.map((q,i) => ({question_id:q.id,score:i ? 1 : q.marks,confidence:1,feedback:'Saved grading feedback.',concept_grades:{},misconceptions:[],outcome:i ? 'partial':'correct'}))};
      body=attempt;
    } else if (path.endsWith('/assessments/page')) body={items:[],next_offset:null,contexts:[],detail:value,attempts:attempt ? [attempt] : []};
    else return route.fallback();
    return route.fulfill({json:body});
  });
  return {bodies,starts:()=>starts,uploads:()=>uploads};
}

for (const [kind,mime] of [['pdf','application/pdf'],['txt','text/plain'],['png','image/png']]) test(`interactive ${kind} answer sheet enters review and canonical grading`, async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  const state=await fixture(page);
  await page.goto('/chat/polish-chat');
  const quiz=page.getByRole('region',{name:'Interactive quiz'});
  await expect(quiz.getByRole('button',{name:'Upload answersheet',exact:true})).toBeVisible();
  await expect(quiz.getByLabel('Upload assessment answer sheet')).toHaveAttribute('accept',/\.pdf.*\.txt/);
  await quiz.getByLabel('Upload assessment answer sheet').setInputFiles({name:`answers.${kind}`,mimeType:mime,buffer:Buffer.from('1. A\n2. Inertia resists changes in motion.')});
  const sheet=page.getByRole('region',{name:'Assessment answer sheet'});
  await expect(sheet.getByRole('radio',{name:'Mass times acceleration',exact:true})).toBeChecked();
  const submit=sheet.getByRole('button',{name:'Confirm text & submit'});
  await expect(submit).toBeDisabled();
  await sheet.getByRole('switch',{name:'I reviewed and corrected all extracted answers'}).check();
  await submit.click();
  await expect(sheet.getByText('Attempt 1 · Attempted',{exact:true})).toBeVisible();
  await expect(sheet.getByRole('region',{name:'Assessment feedback'})).toContainText('1 partially correct');
  expect(state.starts()).toBe(1); expect(state.bodies).toHaveLength(1);
});

test('written assigned assessment can upload directly and downloads a question-paper PDF', async ({page}) => {
  await fixture(page,true);
  await page.goto('/assessments?assessment=sheet-assessment');
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download question paper PDF',exact:true}).click();
  expect((await download).suggestedFilename()).toBe('Forces practice-question-paper.pdf');
  await page.getByLabel('Upload assessment answer sheet').setInputFiles({name:'answers.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF fixture')});
  await expect(page.getByLabel('Answer 2',{exact:true})).toHaveValue('Inertia resists changes in motion.');
});

test('regular chat attachment updates the existing interactive card and the new review card', async ({page}) => {
  await fixture(page);
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('region',{name:'Interactive quiz'})).toBeVisible();
  await page.getByLabel('Upload chat files').setInputFiles({name:'answers.txt',mimeType:'text/plain',buffer:Buffer.from('1. A\n2. Inertia resists changes in motion.')});
  await page.getByRole('textbox',{name:'Ask Mentra anything'}).fill('Evaluate my answers for this assessment.');
  await page.getByRole('button',{name:'Send message',exact:true}).click();
  await expect(page.getByRole('region',{name:'Assessment answer sheet'})).toHaveCount(2);
  await expect(page.getByRole('region',{name:'Interactive quiz'})).toHaveCount(0);
  const first=page.getByRole('region',{name:'Assessment answer sheet'}).first();
  await first.getByRole('switch',{name:'I reviewed and corrected all extracted answers'}).check();
  await first.getByRole('button',{name:'Confirm text & submit'}).click();
  await expect(page.getByText('Attempt 1 · Attempted',{exact:true})).toHaveCount(2);
});

test('failed upload retries the same attempt and upload receipt', async ({page}) => {
  const state=await fixture(page,false,true);
  await page.goto('/chat/polish-chat');
  await page.getByLabel('Upload assessment answer sheet').setInputFiles({name:'answers.txt',mimeType:'text/plain',buffer:Buffer.from('1. A\n2. Inertia.')});
  await page.getByRole('button',{name:'Retry upload',exact:true}).click();
  await expect(page.getByRole('region',{name:'Assessment answer sheet'})).toBeVisible();
  expect(state.starts()).toBe(1); expect(state.uploads()).toBe(1);
});

test('self-reported AI use shows the adjusted total with original correctness', async ({page},info) => {
  const state=await fixture(page);
  await page.goto('/chat/polish-chat');
  await page.getByLabel('Upload assessment answer sheet').setInputFiles({name:'answers.txt',mimeType:'text/plain',buffer:Buffer.from('1. A\n2. Inertia.')});
  const sheet=page.getByRole('region',{name:'Assessment answer sheet'});
  await chooseOption(sheet.getByLabel('Assistance used',{exact:true}),'assisted');
  await sheet.getByRole('switch',{name:'I reviewed and corrected all extracted answers'}).check();
  await sheet.getByRole('button',{name:'Confirm text & submit'}).click();
  const feedback=sheet.getByRole('region',{name:'Assessment feedback'});
  await expect(feedback).toContainText('Final result: 2.7/5');
  await expect(feedback).toContainText('Raw score: 3/5.');
  await expect(feedback).toContainText('0.9× final-score adjustment applied');
  await expect(feedback).toContainText('1 correct');
  expect(state.bodies[0].assistance).toBe('assisted');
  await feedback.getByText('Final result: 2.7/5',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath('assisted-score.png'),animations:'disabled'});
});

test('assistance selected in the quiz is retained when switching to an answer sheet', async ({page}) => {
  await fixture(page);
  await page.goto('/chat/polish-chat');
  const quiz=page.getByRole('region',{name:'Interactive quiz'});
  await quiz.getByRole('radio',{name:'Mass times acceleration',exact:true}).check();
  await quiz.getByRole('button',{name:'Next',exact:true}).click();
  await quiz.getByRole('textbox',{name:'Answer question 2'}).fill('My saved answer.');
  await chooseOption(quiz.getByLabel('Quiz assistance used',{exact:true}),'assisted');
  await quiz.getByLabel('Upload assessment answer sheet').setInputFiles({name:'answers.txt',mimeType:'text/plain',buffer:Buffer.from('1. A\n2. Inertia.')});
  await expect(page.getByRole('region',{name:'Assessment answer sheet'}).getByRole('combobox',{name:'Assistance used'})).toContainText('I used AI or hints');
});
