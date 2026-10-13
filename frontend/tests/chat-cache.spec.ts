import { test, expect, type Page } from '@playwright/test';

async function setup(page: Page) {
  const selection = { mode: 'STANDARD' };
  const chats = Array.from({ length: 15 }, (_, i) => ({ id: `cache-${i}`, title: `Cached chat ${i}`, revision: 1,
    message_count: i ? 2 : 48, selection, created_at: '2026-10-12T00:00:00Z', updated_at: '2026-10-12T00:00:00Z', deleted_at: null }));
  const histories = chats.map(chat => Array.from({ length: chat.message_count }, (_, i) => ({ id: `${chat.id}-${i+1}`, conversation_id: chat.id,
    sequence: i+1, role: i % 2 ? 'assistant' : 'user', content: `Saved message ${i+1}`, created_at: chat.created_at })));
  const requests: { id: string; after: number | null; before: number | null; count: number }[] = [];
  let cursor = 1;
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname;
    let body: unknown = [];
    if (path.endsWith('/auth/me')) body = { learner_id: 'cache-user', username: 'learner', user_id: null, provider: null };
    else if (path.endsWith('/student-profile')) body = { learner_id: 'cache-user', details: { education_level: 'college', field_of_study: 'Physics', learning_goal: 'Understand motion', learning_preference: 'balanced', explanation_depth: 'standard' },
      estimates: Object.fromEntries(['overall_proficiency', 'reasoning', 'quantitative', 'comprehension', 'domain_familiarity'].map(key => [key, { value: null, confidence: 0, evidence_count: 0 }])),
      onboarding_phase: 'complete', calibration_status: 'skipped', evaluation_status: 'not_started', version: 1, context_version: 1 };
    else if (path.endsWith('/conversations/sync')) body = { reset: false, cursor, has_more: false,
      conversations: Number(url.searchParams.get('cursor')) === cursor ? [] : chats, deleted_ids: [], list_cursor: null };
    else if (/\/(status|messages)$/.test(path)) {
      const id = path.split('/').at(-2)!, index = chats.findIndex(chat => chat.id === id);
      if (index < 0) {
        requests.push({ id, after:null, before:null, count:0 });
        await route.fulfill({ status:404, json:{ error:{ code:'CHAT_NOT_FOUND', message:'Conversation not found.' } } });
        return;
      }
      const after = url.searchParams.has('after') ? Number(url.searchParams.get('after')) : null;
      const before = url.searchParams.has('before') ? Number(url.searchParams.get('before')) : null;
      const candidates = histories[index].filter(message => (after === null || message.sequence > after) && (before === null || message.sequence < before));
      const items = after === null ? candidates.slice(-40) : candidates.slice(0, 40);
      const more = candidates.length > 40;
      requests.push({ id, after, before, count: items.length });
      body = { conversation: chats[index], items, incremental: after !== null, has_more: more,
        next_cursor: more ? (after === null ? items[0].sequence : items.at(-1)!.sequence) : null, turn: null };
    } else if (path.endsWith('/conversations/turns') && route.request().method() === 'POST') {
      const sent = route.request().postDataJSON();
      await new Promise(resolve => setTimeout(resolve, 400));
      const chat = {...chats[1], id:sent.conversation_id, title:'New saved chat', revision:3, message_count:2};
      const messages = [{id:'new-user', conversation_id:chat.id, sequence:1, role:'user', content:sent.content, created_at:chat.created_at},
        {id:'new-answer', conversation_id:chat.id, sequence:2, role:'assistant', content:'A saved answer', created_at:chat.created_at}];
      chats.push(chat); histories.push(messages); cursor++;
      body = {conversation:chat, items:messages, incremental:true, has_more:false, next_cursor:null,
        turn:{id:sent.client_turn_id, attempt:1, state:'SUCCEEDED', user_sequence:1, selection}};
    } else if (path.endsWith('/notifications/unread-count')) body = { count: 0 };
    else if (path.endsWith('/assessments/preferences')) body = { auto_add: false, revision: 1 };
    await route.fulfill({ json: body });
  });
  await page.goto('/chat/cache-0');
  await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeEnabled();
  return { requests, append(count: number) {
    const chat = chats[0], history = histories[0];
    for (let i = 0; i < count; i++) history.push({ id: `${chat.id}-${history.length+1}`, conversation_id: chat.id,
      sequence: history.length+1, role: i % 2 ? 'assistant' : 'user', content: `Other device message ${history.length+1}`, created_at: chat.created_at });
    chat.message_count = history.length; chat.revision++; cursor++;
  }, correct() { histories[0][0].content = 'Database reconciled first message'; chats[0].revision++; cursor++; } };
}

test('new local draft never fetches status before first-send acknowledgement', async ({page}) => {
  const state = await setup(page);
  await page.getByRole('button', {name:'Start a new chat', exact:true}).click();
  await page.getByRole('textbox', {name:'Ask Mentra anything'}).fill('First message in a new conversation');
  await page.getByRole('button', {name:'Send message', exact:true}).click();
  await expect(page.getByText('Conversation not found.', {exact:true})).toHaveCount(0);
  await expect(page.getByText('A saved answer', {exact:true})).toBeVisible();
  expect(state.requests.filter(request=>request.count===0)).toHaveLength(0);
});

test('genuinely missing persisted chat still reports not found', async ({page}) => {
  await setup(page);
  await page.goto('/chat/11111111-1111-4111-8111-111111111111');
  await expect(page.getByText('Conversation not found.', {exact:true})).toBeVisible();
});

test('idle foreground chat appends multiple pages from another device without reloading history', async ({ page }) => {
  const state = await setup(page);
  await page.getByRole('button', { name: 'Load earlier messages' }).click();
  await expect(page.getByRole('article')).toHaveCount(48);
  const initial = state.requests.length;
  state.append(44);
  await expect(page.getByRole('article')).toHaveCount(92, { timeout: 12_000 });
  const updates = state.requests.slice(initial);
  expect(updates.map(request => request.after)).toEqual([48, 88]);
  expect(updates.map(request => request.count)).toEqual([40, 4]);
  await expect(page.getByRole('article').first()).toContainText('Saved message 1');
  await expect(page.getByRole('article').last()).toContainText('Other device message 92');
});

test('revisit shows cached history immediately then reconciles all loaded pages with the database', async ({ page }) => {
  const state = await setup(page);
  await page.getByRole('button', { name: 'Load earlier messages' }).click();
  await expect(page.getByRole('article')).toHaveCount(48);
  await page.getByRole('link', { name: 'Cached chat 1', exact: true }).click();
  await expect(page.getByRole('article')).toHaveCount(2);
  state.correct(); state.append(2);
  const start = state.requests.length;
  await page.getByRole('link', { name: 'Cached chat 0', exact: true }).click();
  await expect(page.getByRole('article').first()).toContainText('Database reconciled first message');
  await expect(page.getByRole('article')).toHaveCount(50);
  expect(state.requests.slice(start).some(request => request.after === null && request.before !== null)).toBe(true);
  await page.reload();
  await expect(page.getByRole('article')).toHaveCount(40);
  await page.getByRole('button', { name: 'Load earlier messages' }).click();
  await expect(page.getByRole('article').first()).toContainText('Database reconciled first message');
});

test('visiting more than twelve chats retains the earlier chats in session memory', async ({ page }) => {
  await setup(page);
  for (let i = 1; i < 15; i++) {
    await page.getByRole('link', { name: `Cached chat ${i}`, exact: true }).click();
    await expect(page.getByRole('textbox', { name: 'Ask Mentra anything' })).toBeEnabled();
  }
  const count = await page.evaluate(async () => {
    const path = '/src/stores/chatStore.ts'; const { chatStore } = await import(path);
    return chatStore.view('cache-0').messages.length;
  });
  expect(count).toBe(40);
});
