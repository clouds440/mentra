import { expect, type Page } from '@playwright/test';
const title = 'A long conversation about understanding motion and forces';
export async function workspace(page: Page, running = false, populated = false, stream = '', selected = false, messageCount = 40) {
  const selection = {mode:selected ? 'SOURCE_SPECIFIC' : 'STANDARD', context_ids:[], document_ids:selected ? ['material-1'] : [], include_archived:false};
  const conversation = {id:'polish-chat', title, revision:2, message_count:messageCount, selection, created_at:'2026-10-11T00:00:00Z', updated_at:'2026-10-11T00:00:00Z', deleted_at:null};
  const file = {id:'image-file', filename:'study.png', size_bytes:1024};
  const items: Record<string, unknown>[] = Array.from({length:messageCount}, (_, i) => ({id:`message-${i}`, conversation_id:conversation.id, sequence:i+1, role:i % 2 ? 'assistant' : 'user', content:`${i === messageCount - 1 ? 'Latest answer' : 'Earlier question and explanation'} ${'Learning takes practice. '.repeat(20)}`, created_at:conversation.created_at, ...(i === 38 ? {attachments:[file]} : {})}));
  let state = running ? 'RUNNING' : 'SUCCEEDED';
  let turnId = 'polish-turn', userSequence = 39;
  const snapshot = () => ({conversation, items, has_more:false, next_cursor:null, turn:{id:turnId, state, attempt:1, user_sequence:userSequence, selection, error:state === 'FAILED' ? 'Response stopped.' : null}});
  const context = {context_id:'context-1', name:'A broader learning context with a longer descriptive name', status:'ACTIVE'};
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/source')) return route.fulfill({contentType:'image/png', body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6YZsAAAAASUVORK5CYII=', 'base64')});
    if (path.includes('/turns/') && path.endsWith('/events')) {
      const after = Number(new URL(route.request().url()).searchParams.get('after') ?? 0);
      const chunks = stream.match(/[\s\S]{1,1500}/g) ?? [''];
      const events = chunks.map((chunk, index) => ({schema_version:1, conversation_id:conversation.id, turn_id:turnId, attempt:1, sequence:index+1, step_id:stream ? 'response-stream' : 'planning', status:'running', tool_name:null, user_message:stream ? 'Writing your response' : 'Planning your request', ...(chunk ? {token_delta:chunk} : {})}));
      return route.fulfill({contentType:'text/event-stream', body:events.filter(event => event.sequence > after).map(event => 'event: activity\ndata: '+JSON.stringify(event)+'\n\n').join('')});
    }
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {learner_id:'polish-user', username:'learner', user_id:null, provider:null};
    else if (path.endsWith('/student-profile')) body = {learner_id:'polish-user', details:{education_level:'college', field_of_study:'Physics', learning_goal:'Understand motion', learning_preference:'balanced', explanation_depth:'standard'}, estimates:Object.fromEntries(['overall_proficiency','reasoning','quantitative','comprehension','domain_familiarity'].map(key => [key,{value:null, confidence:0, evidence_count:0}])), onboarding_phase:'complete', calibration_status:'skipped', evaluation_status:'not_started', version:1, context_version:1};
    else if (path.endsWith('/conversations/sync')) body = {reset:false, cursor:1, has_more:false, conversations:[conversation], deleted_ids:[], list_cursor:null};
    else if (path.endsWith('/conversations/turns')) {
      const request = route.request().postDataJSON();
      turnId = request.client_turn_id; userSequence = ++conversation.message_count;
      state = 'RUNNING'; conversation.revision++;
      items.push({id:`sent-${turnId}`, conversation_id:conversation.id, sequence:userSequence, role:'user', content:request.content, created_at:conversation.created_at});
      body = snapshot();
    }
    else if (path.endsWith('/stop')) { expect(route.request().postDataJSON()).toEqual({attempt:1}); state='FAILED'; conversation.revision++; items.push({id:'stopped', conversation_id:conversation.id, sequence:41, role:'assistant', content:'Response stopped. Ready when you are.', created_at:conversation.created_at}); body = snapshot(); }
    else if (path.endsWith('/status')) {
      const url = new URL(route.request().url());
      body = url.searchParams.has('after') ? { ...snapshot(), incremental:true, items:items.filter(item => Number(item.sequence) > Number(url.searchParams.get('after'))) } : snapshot();
    }
    else if (path.includes('/chat-attachments/')) body = {...file, ready:true, warnings:[], error:null, library_result:null};
    else if (path.endsWith('/documents') || path.endsWith('/documents/page')) body = {items:populated ? [{id:'material-1', title:'Motion and forces', filename:'Physics notes.pdf', context_ids:[context.context_id], jobs:[], active_generation_id:'generation-1', archived:false}] : [], total:populated ? 1 : 0, limit:30, offset:0, contexts:[context]};
    else if (path.endsWith('/learning-contexts')) body = [context];
    else if (path.endsWith('/learning/understanding')) body = {items:populated ? [{concept_id:'forces', name:'Forces', knowledge_status:'developing', mastery:.6, estimate_confidence:.5, retention_confidence:.4}] : [],total:populated ? 1 : 0,total_concepts:populated ? 1 : 0,limit:10,offset:0,generated_at:conversation.created_at};
    else if (path.endsWith('/learning')) body = {learner:{concepts:populated ? [{concept_id:'forces', name:'Forces', knowledge_status:'developing', mastery:.6, estimate_confidence:.5, retention_confidence:.4}] : [], generated_at:conversation.created_at, context_ids:[]}, recommendations:populated ? [{concept_id:'forces', name:'Forces', reason:'A little more practice will help you connect the ideas.'}] : [], verification:[]};
    else if (path.endsWith('/learning/page')) body = {overview:{learner:{concepts:[],generated_at:conversation.created_at,context_ids:[]}, recommendations:populated ? [{concept_id:'forces', name:'Forces', reason:'A little more practice will help you connect the ideas.'}] : [],verification:[]},contexts:[context],candidates:[],understanding:{items:populated ? [{concept_id:'forces',name:'Forces',knowledge_status:'developing',mastery:.6,estimate_confidence:.5,retention_confidence:.4}] : [],total:populated ? 1 : 0,total_concepts:populated ? 1 : 0,limit:10,offset:0,generated_at:conversation.created_at}};
    else if (path.endsWith('/assessments/mistakes')) body = {items:[],total:0,active_count:0,next_offset:null,contexts:[],assessments:[],topics:[]};
    else if (path.endsWith('/assessments/preferences')) body = {auto_add:false, revision:1};
    else if (path.endsWith('/assessments') || path.endsWith('/assessments/page')) body = {items:populated ? [{id:'assessment-1', title:'Understanding forces', questions:[], question_count:0,part_count:0,has_paper:false,purpose:'practice'}] : [], next_offset:null,contexts:[context],detail:null,attempts:[]};
    else if (path.endsWith('/events')) body = {items:populated ? [{id:'event-1', title:'Physics study session', local_date:'2026-10-12', timezone:'UTC', kind:'study', status:'scheduled', bucket:'upcoming'}] : [], next_cursor:null};
    else if (path.endsWith('/events/page')) body = {items:populated ? [{id:'event-1', title:'Physics study session', local_date:'2026-10-12', timezone:'UTC', kind:'study', status:'scheduled', bucket:'upcoming'}] : [],next_cursor:null,detail:null,proposals:[],proposals_error:false};
    else if (path.endsWith('/memories/page')) body = {items:[],next_cursor:null,preferences:{automatic_memory:false,revision:1}};
    else if (path.endsWith('/notifications/unread')) body = {unread_count:0,sync_revision:0};
    else if (path.endsWith('/notifications/unread-count')) body = {count:0};
    else if (path.endsWith('/notifications/preferences')) body = {enabled:true, disabled_kinds:[], revision:1};
    else if (path.endsWith('/notifications')) body = {items:populated ? [{id:'notification-1', title:'Time for a little physics', body:'Your study session is coming up. Pick up where you left off.', created_at:conversation.created_at, read_at:null, target_kind:'event', target_id:'event-1'}] : [], unread_count:populated ? 1 : 0, next_cursor:null};
    else if (path.endsWith('/rag/capabilities')) body = {uploads_enabled:true, max_upload_bytes:1000000, formats:['pdf']};
    await route.fulfill({json:body});
  });
  return {
    keepLastMessages(count: number) { items.splice(0, items.length - count); },
    startWithAnswer() { items.shift(); },
    complete(content: string, warnings: Record<string, unknown>[] = []) {
      state = 'SUCCEEDED'; conversation.revision++; conversation.message_count++;
      items.push({id:`formatted-answer-${conversation.message_count}`, conversation_id:conversation.id, sequence:conversation.message_count, role:'assistant', content, created_at:conversation.created_at, tool_warnings:warnings,
        ...(userSequence === 39 ? {interactions:[{id:'choice-1',kind:'single_choice',question:'Which example next?',options:[{id:'python',label:'Python'},{id:'javascript',label:'JavaScript'}],selected:[],submitted_turn_id:null}]} : {})});
    },
  };
}
