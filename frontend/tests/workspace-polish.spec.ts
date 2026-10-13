import { test, expect, type Page } from '@playwright/test';

const title = 'A long conversation about understanding motion and forces';
test('Copy response exports plain text with intact code and reports clipboard errors', async ({page}) => {
  const state = await workspace(page, true);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {value:{writeText:async (value:string) => { (window as unknown as {copiedText:string}).copiedText = value; }}, configurable:true});
  });
  await page.goto('/chat/polish-chat');
  state.complete('# A **clear** answer\n\nUse `value` and [Python](https://python.org).\n\n```python\ndef example():\n    return "*literal*"\n```\n\n- First point\n- Second point\n\n| Name | Value |\n| --- | --- |\n| Result | 2 |');
  const message = page.getByLabel('Mentra response',{exact:true}).last();
  const copy = message.getByRole('button',{name:'Copy response',exact:true});
  await expect(copy).toBeVisible({timeout:15_000});
  await copy.click();
  await expect(message.getByRole('button',{name:'Response copied'})).toBeVisible();
  const copied = await page.evaluate(() => (window as unknown as {copiedText:string}).copiedText);
  expect(copied).toContain('A clear answer');
  expect(copied).toContain('Use value and Python (https://python.org).');
  expect(copied).toContain('def example():\n    return "*literal*"');
  expect(copied).toContain('Name\tValue\nResult\t2');
  expect(copied).not.toContain('```');
  expect(copied).not.toContain('Copy code');
  expect(copied).not.toContain('Which example next?');
  await page.evaluate(() => { navigator.clipboard.writeText = async () => {throw new Error('Clipboard unavailable');}; });
  await message.getByRole('button',{name:'Response copied'}).click();
  await expect(message.getByRole('status').filter({hasText:'Couldn’t copy'})).toBeVisible();
});
async function workspace(page: Page, running = false, populated = false, stream = '', selected = false) {
  const selection = {mode:selected ? 'SOURCE_SPECIFIC' : 'STANDARD', context_ids:[], document_ids:selected ? ['material-1'] : [], include_archived:false};
  const conversation = {id:'polish-chat', title, revision:2, message_count:40, selection, created_at:'2026-10-11T00:00:00Z', updated_at:'2026-10-11T00:00:00Z', deleted_at:null};
  const file = {id:'image-file', filename:'study.png', size_bytes:1024};
  const items: Record<string, unknown>[] = Array.from({length:40}, (_, i) => ({id:`message-${i}`, conversation_id:conversation.id, sequence:i+1, role:i % 2 ? 'assistant' : 'user', content:`${i === 39 ? 'Latest answer' : 'Earlier question and explanation'} ${'Learning takes practice. '.repeat(20)}`, created_at:conversation.created_at, ...(i === 38 ? {attachments:[file]} : {})}));
  let state = running ? 'RUNNING' : 'SUCCEEDED';
  const snapshot = () => ({conversation, items, has_more:false, next_cursor:null, turn:{id:'polish-turn', state, attempt:1, user_sequence:39, selection, error:state === 'FAILED' ? 'Response stopped.' : null}});
  const context = {context_id:'context-1', name:'A broader learning context with a longer descriptive name', status:'ACTIVE'};
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/source')) return route.fulfill({contentType:'image/png', body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6YZsAAAAASUVORK5CYII=', 'base64')});
    if (path.includes('/turns/') && path.endsWith('/events')) {
      const after = Number(new URL(route.request().url()).searchParams.get('after') ?? 0);
      const chunks = stream.match(/[\s\S]{1,1500}/g) ?? [''];
      const events = chunks.map((chunk, index) => ({schema_version:1, conversation_id:conversation.id, turn_id:'polish-turn', attempt:1, sequence:index+1, step_id:stream ? 'response-stream' : 'planning', status:'running', tool_name:null, user_message:stream ? 'Writing your response' : 'Planning your request', ...(chunk ? {token_delta:chunk} : {})}));
      return route.fulfill({contentType:'text/event-stream', body:events.filter(event => event.sequence > after).map(event => 'event: activity\ndata: '+JSON.stringify(event)+'\n\n').join('')});
    }
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = {learner_id:'polish-user', username:'learner', user_id:null, provider:null};
    else if (path.endsWith('/student-profile')) body = {learner_id:'polish-user', details:{education_level:'college', field_of_study:'Physics', learning_goal:'Understand motion', learning_preference:'balanced', explanation_depth:'standard'}, estimates:Object.fromEntries(['overall_proficiency','reasoning','quantitative','comprehension','domain_familiarity'].map(key => [key,{value:null, confidence:0, evidence_count:0}])), onboarding_phase:'complete', calibration_status:'skipped', evaluation_status:'not_started', version:1, context_version:1};
    else if (path.endsWith('/conversations/sync')) body = {reset:false, cursor:1, has_more:false, conversations:[conversation], deleted_ids:[], list_cursor:null};
    else if (path.endsWith('/stop')) { expect(route.request().postDataJSON()).toEqual({attempt:1}); state='FAILED'; conversation.revision++; items.push({id:'stopped', conversation_id:conversation.id, sequence:41, role:'assistant', content:'Response stopped. Ready when you are.', created_at:conversation.created_at}); body = snapshot(); }
    else if (path.endsWith('/status')) {
      const url = new URL(route.request().url());
      body = url.searchParams.has('after') ? { ...snapshot(), incremental:true, items:items.filter(item => Number(item.sequence) > Number(url.searchParams.get('after'))) } : snapshot();
    }
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
  return {
    complete(content: string, warnings: Record<string, unknown>[] = []) {
      state = 'SUCCEEDED'; conversation.revision++; conversation.message_count++;
      items.push({id:'formatted-answer', conversation_id:conversation.id, sequence:41, role:'assistant', content, created_at:conversation.created_at, tool_warnings:warnings,
        interactions:[{id:'choice-1',kind:'single_choice',question:'Which example next?',options:[{id:'python',label:'Python'},{id:'javascript',label:'JavaScript'}],selected:[],submitted_turn_id:null}]});
    },
  };
}

test('source selection clears once after success and retrieval limits are described accurately', async ({ page }) => {
  const updates: string[] = [];
  page.on('request', request => { if (request.url().includes('/status?after=')) updates.push(request.url()); });
  const state = await workspace(page, true, true, '', true);
  await page.goto('/chat/polish-chat?document=material-1');
  await expect(page.getByText('Using selected material', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Current activity')).toBeVisible();
  state.complete('Answer grounded in the available passages.', [{tool_name:'search_study_material',code:'TOOL_BUDGET',task_impact:'optional',effect_certainty:'read_only'}]);
  await expect(page.getByText('Using selected material', { exact: true })).toHaveCount(0, {timeout:15_000});
  await expect(page).toHaveURL(/\/chat\/polish-chat$/);
  await expect(page.getByLabel('Response limitations')).toHaveCount(0);
  expect(updates.some(url => url.endsWith('after=40'))).toBe(true);
  const input = page.getByRole('textbox', { name: 'Ask Mentra anything' });
  await input.fill('@Motion');
  await page.getByRole('option', { name: /Motion and forces/ }).click();
  await expect(page.getByText('Using selected material', { exact: true })).toBeVisible();
  await page.evaluate(async () => { const path='/src/stores/chatStore.ts'; const { chatStore }=await import(path); await chatStore.sync(); });
  await expect(page.getByText('Using selected material', { exact: true })).toBeVisible();
});

test('stopping a response retains the selected source for retry', async ({ page }) => {
  await workspace(page, true, true, '', true);
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('button', { name: 'Stop response' })).toBeEnabled();
  await page.getByRole('button', { name: 'Stop response' }).click();
  await expect(page.getByText('Response stopped. Ready when you are.')).toBeVisible();
  await expect(page.getByText('Using selected material', { exact: true })).toBeVisible();
});

for (const size of [{width:1280,height:800}, {width:1280,height:400}, {width:390,height:844}, {width:390,height:420}]) {
  test(`formatted answer reveals as a unit and scrolls only inside chat at ${size.width}x${size.height}`, async ({page}, info) => {
    await page.setViewportSize(size);
    const markdown = '## Formatted answer\n\nThis is **important** and uses `inline code`.\n\n- First example\n- Second example\n\n```python\nprint("Hello")\n```\n\n' + 'A readable explanation. '.repeat(150);
    const state = await workspace(page, true, false, markdown);
    await page.goto('/chat/polish-chat');
    const preview = page.getByLabel('Response in progress');
    await expect(page.getByLabel('Current activity')).toBeVisible({timeout:15_000});
    await expect(preview).toHaveCount(0);
    await expect(page.getByRole('heading', {name:'Formatted answer'})).toHaveCount(0);
    const geometry = async () => page.evaluate(() => ({
      documentHeight:document.documentElement.scrollHeight, viewport:innerHeight, windowScroll:scrollY,
      headerTop:document.querySelector('header')!.getBoundingClientRect().top,
      headerHeight:document.querySelector('header')!.getBoundingClientRect().height,
      chatHeight:document.querySelector('[aria-label="Conversation"]')!.clientHeight,
      chatContent:document.querySelector('[aria-label="Conversation"]')!.scrollHeight,
      composerBottom:document.querySelector('[aria-label="Message Mentra"]')!.getBoundingClientRect().bottom,
    }));
    const during = await geometry();
    expect(during.documentHeight).toBeLessThanOrEqual(during.viewport + 1);
    expect(during.headerTop).toBe(0); expect(during.headerHeight).toBe(48);
    expect(during.chatContent).toBeGreaterThan(during.chatHeight);
    expect(during.composerBottom).toBeLessThanOrEqual(during.viewport);
    const chat = page.getByRole('log');
    await chat.hover(); await page.mouse.wheel(0, 2000);
    await expect.poll(async () => (await geometry()).windowScroll).toBe(0);
    if (size.width === 1280) {
      const width = await chat.locator(':scope > div').evaluate(el => el.getBoundingClientRect().width);
      expect(width).toBe(832);
      const composerWidth = await page.getByRole('form', {name:'Message Mentra'}).evaluate(el => el.getBoundingClientRect().width);
      expect(composerWidth).toBe(width);
    }
    state.complete(markdown);
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(preview).toHaveCount(0);
    const final = page.getByRole('article', {name:'Mentra response'}).last();
    await expect(final.getByRole('heading', {name:'Formatted answer'})).toBeVisible();
    await expect(final.locator('strong')).toHaveText('important');
    await expect(final.getByRole('button', {name:'Copy code'})).toBeVisible();
    await expect(final.getByLabel('Interactive question')).toBeVisible();
    await expect(final).toHaveClass(/chat-response-reveal/);
    expect(await final.evaluate(el => getComputedStyle(el).animationDuration)).toBe('1s');
    await expect.poll(() => final.evaluate(el => getComputedStyle(el).clipPath), {timeout:1500, intervals:[50]}).toBe('none');
    const heading = await final.getByRole('heading', {name:'Formatted answer'}).boundingBox();
    const chatBounds = await chat.boundingBox();
    expect(heading!.y).toBeGreaterThanOrEqual(chatBounds!.y);
    expect(heading!.y).toBeLessThan(chatBounds!.y + chatBounds!.height);
    await chat.hover(); await page.mouse.wheel(0, 4000);
    const after = await geometry();
    expect(after.documentHeight).toBeLessThanOrEqual(after.viewport + 1);
    expect(after.headerTop).toBe(0); expect(after.windowScroll).toBe(0);
    expect(after.composerBottom).toBeLessThanOrEqual(after.viewport);
    await page.screenshot({path:info.outputPath('chat-scroll-and-rendering.png'), animations:'disabled'});
  });
}

for (const long of [false, true]) test(`code wheel scroll chains to chat at boundaries (${long ? 'long' : 'short'} block)`, async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  const codeText = long ? Array.from({length:180}, (_, i) => `print(${i})`).join('\n') : 'print("Hello")';
  const state = await workspace(page);
  state.complete('## Code example\n\n```python\n' + codeText + '\n```\n\n' + 'More explanation after the code. '.repeat(250));
  await page.goto('/chat/polish-chat');
  const final = page.getByRole('article', {name:'Mentra response'}).last();
  const code = final.getByRole('region', {name:'Python'});
  const chat = page.getByRole('log');
  await expect(code).toBeVisible({timeout:15_000});
  await expect(final).not.toHaveClass(/chat-response-reveal/); // Restored history stays still.
  await code.evaluate(el => el.scrollIntoView({block:'center'}));
  await code.hover();
  if (long) {
    const chatBefore = await chat.evaluate(el => el.scrollTop);
    await code.evaluate(el => { el.scrollTop = 0; });
    await page.mouse.wheel(0, 150);
    await expect.poll(() => code.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    expect(await chat.evaluate(el => el.scrollTop)).toBe(chatBefore);
    await code.evaluate(el => { el.scrollTop = el.scrollHeight; });
  } else {
    expect(await code.evaluate(el => el.scrollHeight <= el.clientHeight)).toBe(true);
  }
  const before = await chat.evaluate(el => el.scrollTop);
  await page.mouse.wheel(0, 250);
  await expect.poll(() => chat.evaluate(el => el.scrollTop)).toBeGreaterThan(before);
  await code.evaluate(el => { el.scrollTop = 0; });
  await code.hover();
  const beforeUp = await chat.evaluate(el => el.scrollTop);
  await page.mouse.wheel(0, -250);
  await expect.poll(() => chat.evaluate(el => el.scrollTop)).toBeLessThan(beforeUp);
  expect(await page.evaluate(() => scrollY)).toBe(0);
});

test('reduced motion shows the completed answer immediately', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  const state = await workspace(page, true, false, 'A buffered answer.');
  await page.goto('/chat/polish-chat');
  await expect(page.getByLabel('Current activity')).toBeVisible({timeout:15_000});
  state.complete('## Ready immediately\n\nThe answer is formatted.');
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  const final = page.getByRole('article', {name:'Mentra response'}).last();
  await expect(final.getByRole('heading', {name:'Ready immediately'})).toBeVisible();
  expect(await final.evaluate(el => getComputedStyle(el).animationName)).toBe('none');
});

test('global scrollbars are thin, transparent and arrowless in both themes', async ({page}) => {
  const state = await workspace(page);
  state.complete('```python\n' + 'print("hello")\n'.repeat(100) + '```');
  await page.goto('/chat/polish-chat');
  await expect(page.getByRole('log')).toBeVisible({timeout:15_000});
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
    const styles = await page.evaluate(() => [...document.querySelectorAll('[aria-label="Conversation"], .code-scroll')].map(el => ({
      standardWidth:getComputedStyle(el).scrollbarWidth,
      standardColor:getComputedStyle(el).scrollbarColor,
      width:getComputedStyle(el,'::-webkit-scrollbar').width,
      height:getComputedStyle(el,'::-webkit-scrollbar').height,
      arrows:getComputedStyle(el,'::-webkit-scrollbar-button').display,
      arrowHeight:getComputedStyle(el,'::-webkit-scrollbar-button').height,
      track:getComputedStyle(el,'::-webkit-scrollbar-track').backgroundColor,
      corner:getComputedStyle(el,'::-webkit-scrollbar-corner').backgroundColor,
      thumb:getComputedStyle(el,'::-webkit-scrollbar-thumb').backgroundColor,
      clip:getComputedStyle(el,'::-webkit-scrollbar-thumb').backgroundClip,
    })));
    expect(styles).toHaveLength(2);
    for (const style of styles) {
      expect(style.standardWidth).toBe('auto'); expect(style.standardColor).toBe('auto');
      expect(style.width).toBe('6px'); expect(style.height).toBe('6px');
      expect(style.arrows).toBe('none'); expect(style.arrowHeight).toBe('0px');
      expect(style.track).toBe('rgba(0, 0, 0, 0)'); expect(style.corner).toBe('rgba(0, 0, 0, 0)');
      expect(style.thumb).toBe(theme === 'light' ? 'rgb(203, 213, 225)' : 'rgb(51, 65, 85)');
      expect(style.clip).toBe('padding-box');
    }
  }
});

test('floating shell controls leave the full viewport available to chat', async ({page}, info) => {
  await workspace(page);
  await page.goto('/chat/polish-chat');
  const controls = page.getByLabel('Workspace controls');
  await expect(page.getByRole('log')).toBeVisible();
  await expect(page.locator('main')).toHaveCount(1);
  const geometry = await page.locator('main').evaluate(el => ({top:el.getBoundingClientRect().top, height:el.getBoundingClientRect().height, viewport:innerHeight}));
  expect(geometry.top).toBe(0);
  expect(geometry.height).toBe(geometry.viewport);
  await expect(controls).not.toContainText(title);
  await expect(page.locator('header')).toHaveCount(0);
  await page.getByRole('button', {name:'Collapse sidebar'}).click();
  await expect(page.getByRole('button', {name:'Expand sidebar'})).toBeVisible();
  await controls.getByRole('link', {name:/Notifications/}).click();
  await expect(controls.getByText('Notifications', {exact:true})).toBeVisible();
  await expect(page.getByRole('heading', {name:'Notifications', exact:true})).toBeVisible();
  await page.setViewportSize({width:390, height:844});
  await page.goto('/chat/polish-chat');
  await page.getByRole('button', {name:'Open navigation menu'}).click();
  const sidebar = page.getByRole('complementary', {name:'Main navigation'});
  await expect(sidebar.getByRole('link', {name:'Library', exact:true})).toBeVisible();
  await sidebar.getByRole('button', {name:'Close navigation menu'}).click();
  expect(await page.locator('main').evaluate(el => el.getBoundingClientRect().height)).toBe(844);
  await page.screenshot({path:info.outputPath('floating-chat-mobile.png'), animations:'disabled'});
});

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
  await expect(page.getByLabel('Attachment study.png').getByRole('button', {name:'Open study.png',exact:true})).toBeVisible();
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
