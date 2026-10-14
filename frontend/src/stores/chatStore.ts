import { useSyncExternalStore } from 'react';
import * as api from '../services/conversations';
import { ApiError } from '../services/api';
import { chatErrorMessage } from '../services/userError';
import { ChatCache } from './chatCache';
import type { Conversation, MessagePage, PendingTurn, StoredMessage, Turn } from '../types/conversations';
import type { ChatSelection } from '../types/rag';

interface ChatView {
  messages: StoredMessage[]; loading: boolean; busy: boolean; error: string | null;
  before: number | null; olderWindow: boolean; revision: number; turn: Turn | null;
  unsent: string | null;
}
const empty: ChatView = { messages: [], loading: false, busy: false, error: null, before: null, olderWindow: false, revision: 0, turn: null, unsent: null };
interface ListView { items: Conversation[]; loading: boolean; error: string | null; more: boolean }

class ChatStore {
  private opened = new Set<string>();
  owner: string | null = null;
  private cache: ChatCache | null = null;
  private controller = new AbortController();
  private listeners = new Set<() => void>();
  private chatListeners = new Map<string, Set<() => void>>();
  private chats = new Map<string, Conversation>();
  private deleted = new Set<string>();
  private views = new Map<string, ChatView>();
  private loadedMessages = new Map<string, Map<number, StoredMessage>>();
  private sequences = new Map<string, number>();
  private pending = new Map<string, PendingTurn>();
  private loads = new Map<string, Promise<void>>();
  private drafts = new Set<string>();
  markDraft(id: string) { this.drafts.add(id); }
  private cursor: number | null = null;
  private listCursor: string | null = null;
  private syncing: Promise<void> | null = null;
  private channel: BroadcastChannel | null = null;
  private pollers = new Map<string, ReturnType<typeof setTimeout>>();
  private responseStarts = new Map<string, number>();
  private list: ListView = { items: [], loading: true, error: null, more: false };
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  snapshot = () => this.list;
  subscribeChat = (id: string, fn: () => void) => {
    let values = this.chatListeners.get(id); if (!values) { values = new Set(); this.chatListeners.set(id, values); }
    values.add(fn); return () => { values!.delete(fn); };
  };
  view = (id: string) => this.views.get(id) ?? empty;
  conversation = (id: string) => this.chats.get(id);
  private publish() {
    this.list = { ...this.list, items: [...this.chats.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.id.localeCompare(a.id)), more: !!this.listCursor };
    this.listeners.forEach(fn => fn());
  }
  private setView(id: string, patch: Partial<ChatView>) {
    const previous = this.view(id); this.views.delete(id);
    this.views.set(id, { ...previous, ...patch }); this.chatListeners.get(id)?.forEach(fn => fn());
  }
  private mergeChats(rows: Conversation[]) {
    for (const row of rows) {
      if (this.deleted.has(row.id)) continue;
      const previous = this.chats.get(row.id);
      if (!previous || previous.revision <= row.revision) this.chats.set(row.id, row);
    }
  }
  private alive(signal: AbortSignal) { return !signal.aborted && signal === this.controller.signal; }
  private async persist(action: () => Promise<unknown>) { try { await action(); } catch { /* PostgreSQL remains authoritative when cache storage is unavailable. */ } }
  async start(owner: string) {
    if (this.owner === owner) return;
    this.stop(!!this.owner); this.owner = owner; this.cache = new ChatCache(owner);
    const cache = this.cache, signal = this.controller.signal;
    this.channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(`mentra-chat-${owner}`);
    if (this.channel) this.channel.onmessage = () => { void this.sync(); };
    try {
      const stored = await cache.hydrate(); if (!this.alive(signal)) return;
      this.mergeChats(stored.conversations); this.cursor = stored.cursor; this.listCursor = stored.listCursor;
      stored.pending.forEach(value => this.pending.set(value.conversation_id, value));
      this.publish();
    } catch { /* Start from the server when the cache cannot be read. */ }
    if (!this.alive(signal)) return;
    await this.sync();
    if (this.alive(signal)) for (const id of this.pending.keys()) void this.open(id);
  }
  stop(clear = false) {
    this.controller.abort(); this.controller = new AbortController(); this.channel?.close(); this.channel = null;
    this.pollers.forEach(timer => clearTimeout(timer)); this.pollers.clear();
    this.responseStarts.clear();
    if (this.cache) void this.cache.close(clear).catch(() => {});
    this.owner = null; this.cache = null; this.cursor = null; this.listCursor = null; this.syncing = null;
    this.opened.clear(); this.chats.clear(); this.deleted.clear(); this.pending.clear(); this.loads.clear(); this.views.clear(); this.loadedMessages.clear(); this.sequences.clear();
    this.drafts.clear();
    this.list = { items: [], loading: true, error: null, more: false }; this.publish();
    this.chatListeners.forEach(values => values.forEach(fn => fn()));
  }
  sync() {
    if (!this.owner) return Promise.resolve();
    if (this.syncing) return this.syncing;
    const signal = this.controller.signal, cache = this.cache!;
    const operation = (async () => {
      try {
        let more = true;
        while (more && this.alive(signal)) {
          const page = await api.syncChats(this.cursor, undefined, signal);
          if (!this.alive(signal)) return;
          if (page.reset) {
            this.opened.clear(); this.chats.clear(); this.listCursor = page.list_cursor ?? null;
          }
          this.mergeChats(page.conversations);
          for (const id of page.deleted_ids) {
            this.deleted.add(id);
            this.loadedMessages.delete(id); this.sequences.delete(id);
            this.chats.delete(id); this.pending.delete(id); this.setView(id, { ...empty, error: 'This conversation was deleted.' });
          }
          this.cursor = page.cursor; more = page.has_more;
          await this.persist(() => cache.apply(page.conversations, [], page.deleted_ids, page.cursor, page.reset ? this.listCursor : undefined, page.reset));
          if (!this.alive(signal)) return;
          this.list = { ...this.list, loading: false, error: null }; this.publish();
          for (const [id, listeners] of this.chatListeners) {
            const view = this.views.get(id), row = this.chats.get(id);
            if (listeners.size && view && row && view.revision < row.revision) void this.open(id, false, true);
          }
          if (page.reset) for (const [id, values] of this.chatListeners) { if (values.size && this.views.has(id)) void this.open(id, true); }
        }
      } catch (error) {
        if (!this.alive(signal)) return;
        this.list = { ...this.list, loading: false, error: this.error(error) }; this.publish();
      }
    })();
    this.syncing = operation;
    void operation.finally(() => { if (this.syncing === operation) this.syncing = null; });
    return operation;
  }
  async more() {
    if (!this.listCursor || this.list.loading) return;
    const signal = this.controller.signal, cache = this.cache!;
    this.list = { ...this.list, loading: true }; this.publish();
    try {
      const page = await api.listChats(this.listCursor, signal); if (!this.alive(signal)) return;
      this.mergeChats(page.items); this.listCursor = page.next_cursor;
      await this.persist(() => cache.apply(page.items, [], [], undefined, this.listCursor));
      if (this.alive(signal)) { this.list = { ...this.list, loading: false }; this.publish(); }
    } catch (error) { if (this.alive(signal)) { this.list = { ...this.list, loading: false, error: this.error(error) }; this.publish(); } }
  }
  open(id: string, refresh = false, updates = false): Promise<void> {
    if (!this.owner) return Promise.resolve();
    const existing = this.loads.get(id); if (existing) return existing;
    const view = this.view(id), chat = this.chats.get(id);
    if (!chat && this.drafts.has(id) && (!this.pending.has(id) || view.busy)) return Promise.resolve();
    if (view.busy && this.pending.has(id) && !refresh && !updates) return Promise.resolve();
    if (!refresh && !updates && this.opened.has(id) && view.revision === chat?.revision && !view.busy) return Promise.resolve();
    const signal = this.controller.signal, cache = this.cache!;
    if (!updates) this.setView(id, { loading: true });
    let reconciled = false;
    const operation = (async () => {
      try {
        if (!view.messages.length) {
          const cached = await cache.messages(id).catch(() => []);
          if (this.alive(signal) && cached.length) this.setView(id, { messages: cached, before: cached[0].sequence > 1 ? cached[0].sequence : null });
        }
        const loaded = this.loadedMessages.get(id);
        const oldest = loaded?.size ? [...loaded.keys()].reduce((a, b) => Math.min(a, b)) : undefined;
        let page = await api.getTurn(id, signal, false, updates ? this.sequences.get(id) : undefined);
        if (!this.alive(signal)) return;
        await this.applyPage(page);
        while (page.incremental && page.has_more && page.next_cursor !== null && this.alive(signal) && !this.deleted.has(id)) {
          page = await api.getTurn(id, signal, false, page.next_cursor);
          if (!this.alive(signal)) return;
          await this.applyPage(page);
        }
        // Revisit reconciles every previously loaded page, without downloading unseen history.
        let before = !updates && page.has_more ? page.items[0]?.sequence : undefined;
        while (before !== undefined && oldest !== undefined && before > oldest && this.alive(signal) && !this.deleted.has(id)) {
          const history = await api.getMessages(id, before, signal);
          if (!this.alive(signal)) return;
          await this.applyPage({ ...history, incremental: true, turn: page.turn });
          const next = history.has_more ? history.items[0]?.sequence : undefined;
          if (next === undefined || next >= before) break;
          before = next;
        }
        this.opened.add(id);
        reconciled = true;
        if (this.alive(signal) && page.turn?.state === 'RUNNING' && (!updates || !view.busy)) this.poll(id);
      } catch (error) { if (this.alive(signal)) this.setView(id, { loading: false, error: this.error(error) }); }
    })();
    this.loads.set(id, operation);
    void operation.finally(() => {
      if (this.loads.get(id) !== operation) return;
      this.loads.delete(id);
      if (reconciled && this.alive(signal) && !this.deleted.has(id) && this.chatListeners.get(id)?.size && this.view(id).revision < (this.chats.get(id)?.revision ?? 0)) void this.open(id, false, true);
    });
    return operation;
  }
  private async applyPage(page: MessagePage, older = false) {
    const signal = this.controller.signal, cache = this.cache!;
    const id = page.conversation.id, view = this.view(id);
    this.drafts.delete(id);
    const pendingAtPublication = this.pending.get(id);
    // A poll started before Send can arrive after the next optimistic exchange.
    // It must not retire the new indicator or replace it with the previous turn.
    if (pendingAtPublication && view.busy && page.turn?.id !== pendingAtPublication.client_turn_id) return;
    if (this.deleted.has(id)) return;
    if (page.conversation.revision < view.revision) return;
    this.mergeChats([page.conversation]);
    const loaded = this.loadedMessages.get(id) ?? new Map<number, StoredMessage>();
    page.items.forEach(message => loaded.set(message.sequence, message));
    this.loadedMessages.set(id, loaded);
    if (page.items.length) this.sequences.set(id, Math.max(this.sequences.get(id) ?? 0, ...page.items.map(message => message.sequence)));
    const values = new Map<number, StoredMessage>();
    if (older || page.incremental) view.messages.forEach(message => values.set(message.sequence, message));
    else loaded.forEach(message => values.set(message.sequence, message));
    page.items.forEach(message => values.set(message.sequence, message));
    const items = [...values.values()].sort((a,b) => a.sequence - b.sequence);
    const messages = older || page.incremental && view.olderWindow ? items.slice(0, 200) : items.slice(-200);
    this.setView(id, { messages, loading: false, busy: page.turn?.state === 'RUNNING',
      error: page.turn?.state === 'FAILED' && page.turn.error !== 'Response stopped.' ? chatErrorMessage(page.turn.error) : null, turn: page.turn ?? view.turn,
      before: messages[0]?.sequence > 1 ? messages[0].sequence : null,
      olderWindow: older && items.length > 200 || (older || page.incremental) && view.olderWindow,
      revision: page.conversation.revision });
    this.publish();
    await this.persist(() => cache.apply([page.conversation], page.items, []));
    if (!this.alive(signal)) return;
    // The answer is visible before IndexedDB finishes. A new send may already
    // own this chat; an older completion must not clear its retry state/timer.
    if (this.pending.get(id) !== pendingAtPublication || this.view(id).busy) return;
    if (page.turn && page.turn.state !== 'RUNNING') {
      const started = this.responseStarts.get(id);
      if (started !== undefined) {
        performance.measure('mentra.chat.response_visible', { start: started });
        this.responseStarts.delete(id);
      }
      const timer = this.pollers.get(id);
      if (timer) { clearTimeout(timer); this.pollers.delete(id); }
      this.pending.delete(id); await this.persist(() => cache.pending(null, id));
    }
  }
  async receiveTerminal(id: string, turnId: string, attempt: number, data: unknown) {
    if (!this.owner || !this.cache || this.deleted.has(id)) return;
    const page = data as Partial<MessagePage> | null;
    const current = this.view(id).turn;
    if (current && (current.id !== turnId || current.attempt !== attempt)) return;
    if (!page?.conversation || page.conversation.id !== id || !Number.isInteger(page.conversation.revision)
        || typeof page.conversation.updated_at !== 'string' || !Array.isArray(page.items)
        || page.items.some(item => !item || item.conversation_id !== id || typeof item.id !== 'string'
          || typeof item.content !== 'string' || !Number.isInteger(item.sequence)
          || !['user', 'assistant'].includes(item.role))
        || page.turn?.id !== turnId || page.turn.attempt !== attempt
        || !['SUCCEEDED', 'FAILED'].includes(page.turn.state)) {
      await this.open(id, false, true); return;
    }
    // The SSE terminal packet is the same canonical page as /status. Reconcile
    // its revision directly instead of adding another network/database round trip.
    await this.applyPage(page as MessagePage);
  }
  async stopResponse(id: string) {
    const turn = this.view(id).turn, signal = this.controller.signal;
    if (!this.owner || !turn || turn.state !== 'RUNNING') return;
    try {
      const page = await api.stopTurn(id, turn.id, turn.attempt, signal);
      if (this.alive(signal)) { await this.applyPage(page); this.channel?.postMessage({ changed:true }); }
    } catch (error) { if (this.alive(signal)) this.setView(id, {error:this.error(error)}); }
  }

  async older(id: string) {
    const view = this.view(id); if (!view.before || view.loading) return;
    const signal = this.controller.signal;
    this.setView(id, { loading: true });
    try { const page = await api.getMessages(id, view.before, signal); if (this.alive(signal)) await this.applyPage({ ...page, turn: view.turn }, true); }
    catch (error) { if (this.alive(signal)) this.setView(id, { loading: false, error: this.error(error) }); }
  }
  async send(id: string, content: string, retrieval: ChatSelection, retry = false, attachments: import('../services/chatAttachments').ChatAttachment[] = [], interactionResponse?: import('../types/interactions').InteractionResponse) {
    if (!this.owner || this.view(id).busy) return;
    if (this.view(id).olderWindow) {
      const signal = this.controller.signal;
      await this.open(id, true);
      if (!this.alive(signal) || this.view(id).busy) return;
    }
    const view = this.view(id), signal = this.controller.signal, cache = this.cache!;
    let body = this.pending.get(id);
    if (retry && !body && view.turn?.state === 'FAILED') {
      const message = view.messages.find(item => item.sequence === view.turn!.user_sequence);
      if (!message) return;
      body = { conversation_id: id, client_turn_id: view.turn.id, expected_revision: view.revision, content: message.content, timezone: message.timezone, interaction_response: message.interaction_response, retrieval: view.turn.selection, attachment_ids: view.turn.attachment_ids ?? [] };
    }
    body ??= { conversation_id: id, client_turn_id: crypto.randomUUID(), expected_revision: this.chats.get(id)?.revision ?? 0, content, retrieval, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, interaction_response: interactionResponse, attachment_ids: attachments.map(file => file.id) };
    body = { ...body, retry };
    this.pending.set(id, body);
    const started = performance.now();
    this.responseStarts.set(id, started);
    const optimistic: StoredMessage = { id: body.client_turn_id, conversation_id: id, sequence: (this.chats.get(id)?.message_count ?? 0) + 1,
      role: 'user', content: body.content, attachments, created_at: new Date().toISOString() };
    // Publish the new exchange and its pending indicator together. Publishing
    // busy first mounted activity under the previous exchange, then removed it.
    this.setView(id, { busy: true, error: null, unsent: null, turn: null, olderWindow: false, messages: retry ? view.messages : [...view.messages, optimistic].slice(-200) });
    await this.persist(() => cache.pending(body!, id));
    if (!this.alive(signal)) return;
    try {
      const page = await api.sendTurn(body, signal); if (!this.alive(signal)) return;
      performance.measure('mentra.chat.acknowledged', { start: started });
      await this.applyPage(page);
      if (!this.alive(signal)) return;
      if (body.interaction_response) {
        const reply = body.interaction_response;
        this.setView(id, { messages: this.view(id).messages.map(message => message.id === reply.message_id ? {
          ...message, interactions: message.interactions?.map(card => card.id === reply.interaction_id ? { ...card, selected: reply.selected, submitted_turn_id: body!.client_turn_id } : card)
        } : message) });
      }
      this.channel?.postMessage('changed');
      if (page.turn?.state === 'RUNNING') this.poll(id);
      void this.sync();
    } catch (error) {
      if (!this.alive(signal)) return;
      if (this.deleted.has(id)) return;
      if (error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status)) {
        this.pending.delete(id); await this.persist(() => cache.pending(null, id));
        this.setView(id, { busy: false, error: this.error(error), messages: view.messages, unsent: body.content });
        void this.sync();
      } else {
        this.setView(id, { busy: false, error: 'The connection was interrupted.' });
        void this.open(id, true);
      }
    }
  }
  private poll(id: string, attempt = 0) {
    if (this.pollers.has(id)) return;
    const signal = this.controller.signal;
    this.pollers.set(id, setTimeout(async () => {
      this.pollers.delete(id); if (!this.alive(signal)) return;
      await this.open(id, false, true);
      if (this.alive(signal) && this.view(id).busy && attempt < 50) this.poll(id, attempt + 1);
    }, Math.min(2000 + attempt * 500, 10000)));
  }
  async rename(id: string, title: string) {
    const chat = this.chats.get(id); if (!chat) return;
    const signal = this.controller.signal, cache = this.cache!;
    try {
      const row = await api.renameChat(chat, title, signal); if (!this.alive(signal)) return;
      this.mergeChats([row]); this.publish(); await this.persist(() => cache.apply([row], [], []));
      this.channel?.postMessage('changed'); void this.sync();
    } catch (error) { if (this.alive(signal)) { this.list = { ...this.list, error: this.error(error) }; this.publish(); void this.sync(); } }
  }
  async remove(id: string) {
    const chat = this.chats.get(id); if (!chat) return false;
    const signal = this.controller.signal, cache = this.cache!;
    try {
      await api.deleteChat(chat, signal); if (!this.alive(signal)) return false;
      this.deleted.add(id); this.chats.delete(id); this.pending.delete(id); this.setView(id, empty); this.publish();
      this.loadedMessages.delete(id); this.sequences.delete(id);
      await this.persist(() => cache.apply([], [], [id])); this.channel?.postMessage('changed'); void this.sync(); return true;
    } catch (error) { if (this.alive(signal)) { this.list = { ...this.list, error: this.error(error) }; this.publish(); void this.sync(); } return false; }
  }
  private error(error: unknown) { return error instanceof ApiError ? error.message : 'Your chats could not be loaded.'; }
  hasPending(id: string) { return this.pending.has(id); }
  clearUnsent(id: string) { this.setView(id, { unsent: null, error: null }); }
}
export const chatStore = new ChatStore();
export const useChatList = () => useSyncExternalStore(chatStore.subscribe, chatStore.snapshot);
export function useConversation(id: string) {
  return useSyncExternalStore(fn => chatStore.subscribeChat(id, fn), () => chatStore.view(id));
}
