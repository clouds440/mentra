import type { Page } from '@playwright/test';
import { workspace } from './renovation-fixtures';

export async function richChat(page: Page, content = '', interactions: Record<string, unknown>[] = []) {
  await workspace(page);
  const conversation = { id: 'polish-chat', title: 'Interactive examples', revision: 2, message_count: 2, selection: { mode: 'STANDARD', context_ids: [], document_ids: [] }, created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00Z' };
  const items: Record<string, unknown>[] = [{ id: 'u', conversation_id: conversation.id, sequence: 1, role: 'user', content: 'Explain this concept', created_at: conversation.created_at }, { id: 'a', conversation_id: conversation.id, sequence: 2, role: 'assistant', content, interactions, created_at: conversation.created_at }];
  let turn: Record<string, unknown> | null = null;
  const snapshot = () => ({ conversation, items, has_more: false, next_cursor: null, turn });
  let reads = 0;
  await page.route('**/api/v1/conversations/polish-chat/status*', route => { reads++; return route.fulfill({ json: snapshot() }); });
  await page.route('**/api/v1/conversations/sync*', route => route.fulfill({ json: { conversations: [conversation], reset: false, cursor: conversation.revision, has_more: false, deleted_ids: [], list_cursor: null } }));
  const submissions: Record<string, unknown>[] = [];
  await page.route('**/api/v1/conversations/turns', route => {
    const body = route.request().postDataJSON(); submissions.push(body);
    const reply = body.interaction_response;
    if (reply) {
      const card = interactions.find(item => item.id === reply.interaction_id)!;
      Object.assign(card, { ...reply, submitted_turn_id: body.client_turn_id });
    }
    conversation.revision++; conversation.message_count++;
    items.push({ id: 'answer-' + conversation.message_count, conversation_id: conversation.id, sequence: conversation.message_count, role: 'user', content: body.content, created_at: conversation.created_at });
    turn = { id: body.client_turn_id, state: 'SUCCEEDED', attempt: 1, user_sequence: conversation.message_count, selection: conversation.selection, error: null };
    return route.fulfill({ json: snapshot() });
  });
  return { submissions, conversation, statusReads: () => reads };
}

export async function trackRichRenders(page: Page, names: string[]) {
  await page.addInitScript(names => {
    type Fiber = { flags: number; child: Fiber | null; sibling: Fiber | null; elementType?: { displayName?: string }; type?: { displayName?: string; name?: string } };
    const watched = new Set(names);
    let previous = new Set<Fiber>();
    const counts: Record<string, number> = {};
    const state = { counts, samples: [] as number[], longTasks: [] as number[] };
    Object.assign(window, { richRenderProfile: state, __REACT_DEVTOOLS_GLOBAL_HOOK__: {
      supportsFiber: true, renderers: new Map(), inject: () => 1,
      onCommitFiberRoot: (_renderer: number, root: { current: Fiber }) => {
        const next = new Set<Fiber>();
        function visit(fiber: Fiber | null) {
          while (fiber) {
            next.add(fiber);
            const name = fiber.elementType?.displayName ?? fiber.type?.displayName ?? fiber.type?.name ?? '';
            if (!previous.has(fiber) && (fiber.flags & 1) && watched.has(name)) counts[name] = (counts[name] ?? 0) + 1;
            visit(fiber.child); fiber = fiber.sibling;
          }
        }
        visit(root.current); previous = next;
      }, onCommitFiberUnmount: () => {},
    } });
    new PerformanceObserver(list => state.longTasks.push(...list.getEntries().map(entry => entry.duration))).observe({ type: 'longtask' });
    document.addEventListener('input', () => { const start = performance.now(); requestAnimationFrame(() => state.samples.push(performance.now() - start)); });
  }, names);
}
