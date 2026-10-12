import { test, expect } from '@playwright/test';

for (const packet of ['valid', 'stale', 'invalid'] as const) {
  test(`terminal delivery ${packet}: preserves attempt fencing and avoids redundant reads`, async ({ page }) => {
    const selection = { mode: 'STANDARD', context_ids: [], document_ids: [], include_archived: false };
    const conversation = { id: 'latency-chat', title: 'Latency check', revision: 1, message_count: 1, selection,
      created_at: '2026-10-12T00:00:00Z', updated_at: '2026-10-12T00:00:00Z', deleted_at: null };
    const user = { id: 'question', conversation_id: conversation.id, sequence: 1, role: 'user', content: 'Explain motion', created_at: conversation.created_at };
    const turn = { id: 'latency-turn', attempt: 2, state: 'RUNNING', user_sequence: 1, selection, error: null };
    const running = { conversation, items: [user], turn, has_more: false, next_cursor: null };
    const final = { ...running, conversation: { ...conversation, revision: 2, message_count: 2 },
      items: [user, { ...user, id: 'answer', sequence: 2, role: 'assistant', content: 'Validated final explanation' }],
      turn: { ...turn, state: 'SUCCEEDED' } };
    let delivered = false, reads = 0;
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.includes('/turns/') && path.endsWith('/events')) {
        await gate;
        delivered = true;
        const data = packet === 'invalid' ? {} : packet === 'stale' ? { ...final, turn: { ...final.turn, attempt: 1 } } : final;
        return route.fulfill({ contentType: 'text/event-stream', body: `event: terminal\ndata: ${JSON.stringify(data)}\n\n` });
      }
      let body: unknown = [];
      if (path.endsWith('/auth/me')) body = { learner_id: 'latency-user', username: 'learner', user_id: null, provider: null };
      else if (path.endsWith('/student-profile')) body = { learner_id: 'latency-user', details: { education_level: 'college', field_of_study: 'Physics', learning_goal: 'Learn', learning_preference: 'balanced', explanation_depth: 'standard' }, estimates: {}, onboarding_phase: 'complete', calibration_status: 'skipped', evaluation_status: 'not_started', version: 1, context_version: 1 };
      else if (path.endsWith('/conversations/sync')) body = { reset: false, cursor: 1, has_more: false, conversations: [conversation], deleted_ids: [], list_cursor: null };
      else if (path.endsWith('/status')) { reads++; body = delivered && packet === 'invalid' ? final : running; }
      else if (path.endsWith('/notifications/unread-count')) body = { count: 0 };
      else if (path.endsWith('/assessments/preferences')) body = { auto_add: false, revision: 1 };
      await route.fulfill({ json: body });
    });
    await page.goto('/chat/latency-chat');
    await expect(page.getByRole('button', { name: 'Stop response' })).toBeEnabled();
    const initial = reads;
    release();
    if (packet === 'stale') {
      await expect.poll(() => delivered).toBe(true);
      await expect(page.getByText('Validated final explanation')).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Stop response' })).toBeEnabled();
    } else {
      await expect(page.getByText('Validated final explanation')).toBeVisible();
      expect(reads - initial).toBe(packet === 'valid' ? 0 : 1);
      if (packet === 'valid') {
        const retained = await page.evaluate(async terminal => {
          const path = '/src/stores/chatStore.ts';
          const { chatStore: store } = await import(path);
          const cache = store.cache, apply = cache.apply;
          let finish!: () => void;
          const held = new Promise<void>(resolve => { finish = resolve; });
          cache.apply = () => held;
          try {
            const completion = store.receiveTerminal('latency-chat', 'latency-turn', 2, terminal);
            // Simulate the next send claiming its durable retry state while
            // the previous answer's IndexedDB publication is still pending.
            const next = { client_turn_id: 'next-send' };
            store.pending.set('latency-chat', next);
            finish();
            await completion;
            return store.pending.get('latency-chat') === next;
          } finally {
            cache.apply = apply;
            store.pending.delete('latency-chat');
          }
        }, final);
        expect(retained).toBe(true);
      }
    }
  });
}
