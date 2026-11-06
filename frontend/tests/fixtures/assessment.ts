import type { Page } from '@playwright/test';
import type { AssessmentAttempt } from '../../src/types/assessments';

export async function assessmentFixture(page: Page, { delay = 4000, duplicate = false, incomplete = false,written=false,multiple=false,rtl=false,messages=0,existingAttempt=false,path='/chat/handoff-chat',pageDelay=0 } = {}) {
  const date = '2026-11-05T00:00:00Z', selection = { mode: 'STANDARD' };
  const conversation = { id: 'handoff-chat', title: 'Handoff chat', revision: 3, message_count: 2, selection, created_at: date, updated_at: date, deleted_at: null };
  let assessment = { id: 'handoff-quiz', context_id: 'physics', title: 'Net force', purpose: 'practice', revision: 1, sources: [], created_at: date,
    preferences: { delivery: 'interactive' }, questions: Array.from({ length: 3 }, (_, index) => ({ id: `q-${index}`, answer_mode:written?'text':multiple?'multiple_choice':'single_choice',prompt: rtl ? `كتلة مقدارها أربعة كيلوجرامات وقوة مقدارها ستة نيوتن. ما التسارع؟ (${index+1})` : `A 4 kg block has a net force of 6 N. What is its acceleration? (${index + 1})`, concept_ids: ['force'], marks: 2, difficulty: .3, source_tokens: [], options: written ? [] : [{ id: 'a', label: '1.5 m/s²' }, { id: 'b', label: '24 m/s²' }] })) };
  const card = { id: 'handoff-draft', conversation_id: conversation.id, assessment_id: assessment.id, assessment };
  const generation = { id: 'handoff-card', generation_job_id: 'handoff-job', title: assessment.title };
  const items = [...Array.from({length:messages},(_,index)=>({id:`history-${index}`,conversation_id:conversation.id,sequence:index+1,role:index%2?'assistant':'user',content:`Earlier learning message ${index+1}.`,created_at:date})),{ id: 'question', conversation_id: conversation.id, sequence: messages+1, role: 'user', content: 'Give me a quiz.', created_at: date },
    { id: 'reply', conversation_id: conversation.id, sequence: messages+2, role: 'assistant', content: 'Your quiz is ready.', assessment_cards: [generation], created_at: date },
    ...(duplicate ? [{ id: 'duplicate-preview', conversation_id: conversation.id, sequence: messages+3, role: 'assistant', content: 'The same saved work.', assessment_cards: [{ ...generation, id: 'another-card' }], created_at: date }] : [])];
  const reads: string[] = [],writes:string[]=[]; let completedAt = 0, incomingAttempt: AssessmentAttempt | null = existingAttempt ? {id:'incumbent-attempt',assessment_id:assessment.id,revision:1,state:'draft',attempt_number:1,answers:{},grades:null,extraction:null,error:null,evidence_status:'none',created_at:date,grade_revision:1,grade_history:[]} : null;
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname; reads.push(path);if(request.method()!=='GET')writes.push(path);
    let body: unknown = [];
    if (path.endsWith('/conversations/turns')) body = {conversation,items,has_more:false,next_cursor:null,turn:{id:'adjustment-turn',state:'SUCCEEDED',attempt:1,user_sequence:3,selection,error:null}};
    else if (path.endsWith('/auth/me')) body = { learner_id: 'handoff-user', username: 'handoff-user', user_id: null, provider: null };
    else if (path.endsWith('/student-profile')) body = { learner_id: 'handoff-user', details: { education_level: 'college', field_of_study: 'Physics', learning_goal: 'Learn', learning_preference: 'balanced', explanation_depth: 'standard' }, estimates: Object.fromEntries(['overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity'].map(key => [key, { value: null, confidence: 0, evidence_count: 0 }])), onboarding_phase: 'complete', calibration_status: 'skipped', evaluation_status: 'not_started', version: 1, context_version: 1 };
    else if (path.endsWith('/conversations/sync')) body = { reset: false, cursor: 3, has_more: false, conversations: [conversation], deleted_ids: [], list_cursor: null };
    else if (path.endsWith('/status')) body = { conversation, items, has_more: false, next_cursor: null, turn: { id: 'handoff-turn', state: 'SUCCEEDED', attempt: 1, user_sequence: 1, selection, error: null } };
    else if (path.endsWith('/generation-jobs/handoff-job')) {
      completedAt = Date.now();
      body = { id: 'handoff-job', state: 'completed', title: assessment.title, conversation_id: conversation.id,
        completed_parts: 3, total_parts: 3, result: {...card,assessment}, can_retry: false, revision: 3,
        ...(!incomplete ? { hydration: { version: 1, attempt: incomingAttempt } } : {}) };
    } else if (path.includes('/items/')&&path.endsWith('/report')) {
      const id=path.split('/items/')[1].split('/')[0];assessment={...assessment,revision:assessment.revision+1,questions:assessment.questions.map(q=>q.id===id?{...q,validation:{state:'invalidated'}}:q)};body=assessment;
    } else if (path.endsWith('/chat-drafts/handoff-draft')) {
      await new Promise(resolve => setTimeout(resolve, delay)); body = {...card,assessment,hydration:{version:1,attempt:incomingAttempt}};
    } else if (path.endsWith('/assessments/page')) {
      if(pageDelay)await new Promise(resolve=>setTimeout(resolve,pageDelay));
      body={items:[],next_offset:null,contexts:[{context_id:'physics',name:'Physics',status:'ACTIVE'}],detail:new URL(request.url()).searchParams.has('assessment_id')?assessment:null,attempts:incomingAttempt?[incomingAttempt]:[]};
    } else if (path.endsWith('/handoff-quiz/attempts')) {
      if(request.method()==='POST'){
        incomingAttempt={id:'local-attempt',assessment_id:assessment.id,revision:1,state:'draft',attempt_number:1,answers:{},grades:null,extraction:null,error:null,evidence_status:'none',created_at:date,grade_revision:1,grade_history:[]};
        return route.fulfill({json:incomingAttempt});
      }
      await new Promise(resolve => setTimeout(resolve, delay)); body = [];
    } else if(path.endsWith('/attempts/local-attempt/submission')){
      incomingAttempt={...incomingAttempt!,revision:2,state:'submitted',answers:request.postDataJSON().answers};body=incomingAttempt;
    } else if(path.endsWith('/attempts/local-attempt')){body=incomingAttempt;
    } else if (path.endsWith('/notifications/unread-count')) body = { count: 0 };
    else if (path.endsWith('/assessments/preferences')) body = { auto_add: false, revision: 1 };
    await route.fulfill({ json: body });
  });
  if(rtl)await page.addInitScript(()=>{document.documentElement.dir='rtl';});
  await page.goto(path);
  return { reads,writes,assessment:()=>assessment, completedAt: () => completedAt, quiz: page.getByRole('region', { name: 'Interactive quiz' }),
    completeElsewhere(sameAttempt=false) {
      incomingAttempt = { id: sameAttempt?'incumbent-attempt':'external-attempt', assessment_id: assessment.id, revision: 2, state: 'graded', attempt_number: 1,
        answers: { 'q-0': 'b', 'q-1': 'b', 'q-2': 'b' }, grades: [], extraction: null, error: null,
        evidence_status: 'applied', created_at: date, grade_revision: 1, grade_history: [] };
    } };
}
