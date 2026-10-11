import { test, expect, type Page } from '@playwright/test';

const title = 'A long conversation about understanding motion and forces';
async function workspace(page: Page, running = false, populated = false) {
  const selection = {mode:'STANDARD', context_ids:[], document_ids:[], include_archived:false};
  const conversation = {id:'polish-chat', title, revision:2, message_count:40, selection, created_at:'2026-10-11T00:00:00Z', updated_at:'2026-10-11T00:00:00Z', deleted_at:null};
  const file = {id:'image-file', filename:'study.png', size_bytes:1024};
  const items = Array.from({length:40}, (_, i) => ({id:`message-${i}`, conversation_id:conversation.id, sequence:i+1, role:i % 2 ? 'assistant' : 'user', content:`${i === 39 ? 'Latest answer' : 'Earlier question and explanation'} ${'Learning takes practice. '.repeat(20)}`, created_at:conversation.created_at, ...(i === 38 ? {attachments:[file]} : {})}));
  let state = running ? 'RUNNING' : 'SUCCEEDED';
  const snapshot = () => ({conversation, items, has_more:false, next_cursor:null, turn:{id:'polish-turn', state, attempt:1, user_sequence:39, selection, error:state === 'FAILED' ? 'Response stopped.' : null}});
  const context = {context_id:'context-1', name:'A broader learning context with a longer descriptive name', status:'ACTIVE'};
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/source')) return route.fulfill({contentType:'image/png', body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6YZsAAAAASUVORK5CYII=', 'base64')});
    if (path.includes('/turns/') && path.endsWith('/events')) return route.fulfill({contentType:'text/event-stream', body:'event: activity\ndata: '+JSON.stringify({schema_version:1, conversation_id:conversation.id, turn_id:'polish-turn', attempt:1, sequence:1, step_id:'planning', status:'running', tool_name:null, user_message:'Planning your request'})+'\n\n'});
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {learner_id:'polish-user', username:'learner', user_id:null, provider:null};
    else if (path.endsWith('/student-profile')) body = {learner_id:'polish-user', details:{education_level:'college', field_of_study:'Physics', learning_goal:'Understand motion', learning_preference:'balanced', explanation_depth:'standard'}, estimates:Object.fromEntries(['overall_proficiency','reasoning','quantitative','comprehension','domain_familiarity'].map(key => [key,{value:null, confidence:0, evidence_count:0}])), onboarding_phase:'complete', calibration_status:'skipped', evaluation_status:'not_started', version:1, context_version:1};
    else if (path.endsWith('/conversations/sync')) body = {reset:false, cursor:1, has_more:false, conversations:[conversation], deleted_ids:[], list_cursor:null};
    else if (path.endsWith('/stop')) { expect(route.request().postDataJSON()).toEqual({attempt:1}); state='FAILED'; conversation.revision++; items.push({id:'stopped', conversation_id:conversation.id, sequence:41, role:'assistant', content:'Response stopped. Ready when you are.', created_at:conversation.created_at}); body = snapshot(); }
    else if (path.endsWith('/status')) body = snapshot();
    else if (path.includes('/chat-attachments/')) body = {...file, ready:true, warnings:[], error:null, library_result:null};
    else if (path.endsWith('/documents')) body = {items:populated ? [{id:'material-1', title:'Motion and forces', filename:'Physics notes.pdf', context_ids:[context.context_id], jobs:[], active_generation_id:'generation-1', archived:false}] : [], total:populated ? 1 : 0, limit:30, offset:0};
    else if (path.endsWith('/learning-contexts')) body = [context];
    else if (path.endsWith('/learning')) body = {learner:{concepts:populated ? [{concept_id:'forces', name:'Forces', knowledge_status:'developing', mastery:.6, estimate_confidence:.5, retention_confidence:.4}] : [], generated_at:conversation.created_at, context_ids:[]}, recommendations:populated ? [{concept_id:'forces', name:'Forces', reason:'A little more practice will help you connect the ideas.'}] : [], verification:[]};
    else if (path.endsWith('/assessments/preferences')) body = {auto_add:false, revision:1};
    else if (path.endsWith('/assessments')) body = {items:populated ? [{id:'assessment-1', title:'Understanding forces', questions:[], purpose:'practice'}] : [], next_offset:null};
    else if (path.endsWith('/events')) body = {items:populated ? [{id:'event-1', title:'Physics study session', local_date:'2026-10-12', timezone:'UTC', kind:'study', status:'scheduled', bucket:'upcoming'}] : [], next_cursor:null};
    else if (path.endsWith('/notifications/unread-count')) body = {count:0};
    else if (path.endsWith('/notifications/preferences')) body = {enabled:true, disabled_kinds:[], revision:1};
    else if (path.endsWith('/notifications')) body = {items:populated ? [{id:'notification-1', title:'Time for a little physics', body:'Your study session is coming up. Pick up where you left off.', created_at:conversation.created_at, read_at:null, target_kind:'event', target_id:'event-1'}] : [], unread_count:populated ? 1 : 0, next_cursor:null};
    else if (path.endsWith('/rag/capabilities')) body = {uploads_enabled:true, max_upload_bytes:1000000, formats:['pdf']};
    await route.fulfill({json:body});
  });
}

test('full width titles reveal overlay controls and history opens at the bottom', async ({page}) => {
  await workspace(page, false, true);
  await page.goto('/chat/polish-chat');
  const nav = page.getByRole('link', {name:title, exact:true});
  const actions = page.getByRole('button', {name:`Rename ${title}`}).locator('..');
  await page.getByRole('textbox', {name:'Ask Mentra anything'}).hover();
  await expect(actions).toHaveCSS('opacity', '0');
  const full = await nav.evaluate(el => ({width:el.getBoundingClientRect().width, parent:el.parentElement!.getBoundingClientRect().width, padding:getComputedStyle(el).paddingRight}));
  expect(full.width).toBe(full.parent);
  await nav.hover();
  await expect(actions).toHaveCSS('opacity', '1');
  expect(await nav.evaluate(el => parseFloat(getComputedStyle(el).paddingRight))).toBeGreaterThan(parseFloat(full.padding));
  await expect.poll(() => page.getByRole('log').evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(3);
  await expect(page.getByLabel('Attachment study.png').getByRole('img')).toBeVisible();
  await page.reload();
  await expect.poll(() => page.getByRole('log').evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(3);
  await expect(page.getByLabel('Attachment study.png')).toContainText('Saved in this chat');
  await page.getByRole('link', {name:'Library', exact:true}).click();
  await nav.click();
  await expect.poll(() => page.getByRole('log').evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(3);
  await page.setViewportSize({width:390, height:844});
  await page.getByRole('button', {name:'Open navigation menu'}).click();
  await expect(actions).toHaveCSS('opacity', '1');
  await expect(page.getByText('A quieter way to learn.')).toHaveCount(0);
});

test('Stop replaces Send and the saved stopped response survives reload', async ({page}) => {
  await workspace(page, true);
  await page.goto('/chat/polish-chat');
  await page.getByRole('button', {name:'Stop response', exact:true}).click();
  await expect(page.getByRole('article', {name:'Mentra response'}).last()).toContainText('Response stopped. Ready when you are.');
  await expect(page.getByRole('button', {name:'Send message', exact:true})).toBeVisible();
  await expect(page.getByLabel('Current activity')).toHaveCount(0);
  await expect(page.getByRole('button', {name:'Retry response'})).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('article', {name:'Mentra response'}).last()).toContainText('Response stopped. Ready when you are.');
});

test('workspace pages share responsive surfaces and select options can exceed the trigger', async ({page}, info) => {
  await workspace(page, false, true);
  for (const width of [1280, 390]) {
    await page.setViewportSize({width, height:900});
    for (const path of ['/library', '/library/new', '/progress', '/progress?tab=events', '/assessments', '/assessments?tab=create', '/notifications', '/settings', '/settings?tab=notifications']) {
      await page.goto(path);
      await expect(page.locator('.workspace-header')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (path === '/library') {
        const trigger = page.getByRole('combobox', {name:'Learning context', exact:true});
        await trigger.click();
        const panel = page.getByRole('listbox', {name:'Learning context options'});
        await expect(panel).toBeVisible();
        const menu = await panel.boundingBox(), button = await trigger.boundingBox();
        if (width === 1280) expect(menu!.width).toBeGreaterThan(button!.width + 40);
        expect(menu!.x + menu!.width).toBeLessThanOrEqual(width - 10);
        await page.keyboard.press('Escape');
      }
      if (width === 1280 && path === '/progress?tab=events') {
        const trigger = page.getByRole('combobox', {name:'Event date range'});
        await trigger.click();
        const option = page.getByRole('option', {name:'Upcoming six months'});
        await expect(option).toBeVisible();
        const box = await page.getByRole('listbox', {name:'Event date range options'}).boundingBox();
        const button = await trigger.boundingBox();
        expect(box!.width).toBeGreaterThanOrEqual(button!.width);
        await page.keyboard.press('Escape');
      }
      if (['/settings', '/library', '/notifications', '/progress', '/assessments'].includes(path)) await page.screenshot({path:info.outputPath(`${width}-${path.slice(1)}.png`), animations:'disabled'});
    }
  }
});
