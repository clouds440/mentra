import { useSyncExternalStore } from 'react';
import * as api from '../services/conversations';
import { ApiError } from '../services/api';
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
  owner: string | null = null;
  private cache: ChatCache | null = null;
  private controller = new AbortController();
  private listeners = new Set<() => void>();
  private chatListeners = new Map<string, Set<() => void>>();
  private chats = new Map<string, Conversation>();
  private deleted = new Set<string>();
  private views = new Map<string, ChatView>();
  private pending = new Map<string, PendingTurn>();
  private loads = new Map<string, Promise<void>>();
  private cursor: number | null = null;
  private listCursor: string | null = null;
  private syncing: Promise<void> | null = null;
  private channel: BroadcastChannel | null = null;
  private pollers = new Map<string, ReturnType<typeof setTimeout>>();
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
    if (this.views.size > 12) for (const [key, value] of this.views) {
      if (this.views.size <= 12) break;
      if (!this.chatListeners.get(key)?.size && !value.busy && !this.pending.has(key)) this.views.delete(key);
    }
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
    if (this.cache) void this.cache.close(clear).catch(() => {});
    this.owner = null; this.cache = null; this.cursor = null; this.listCursor = null; this.syncing = null;
    this.chats.clear(); this.deleted.clear(); this.pending.clear(); this.loads.clear(); this.views.clear();
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
            this.chats.clear(); this.listCursor = page.list_cursor ?? null;
          }
          this.mergeChats(page.conversations);
          for (const id of page.deleted_ids) {
            this.deleted.add(id);
            this.chats.delete(id); this.pending.delete(id); this.setView(id, { ...empty, error: 'This conversation was deleted.' });
          }
          this.cursor = page.cursor; more = page.has_more;
          await this.persist(() => cache.apply(page.conversations, [], page.deleted_ids, page.cursor, page.reset ? this.listCursor : undefined, page.reset));
          if (!this.alive(signal)) return;
          this.list = { ...this.list, loading: false, error: null }; this.publish();
          for (const row of page.conversations) {
            const view = this.views.get(row.id);
            if (view && this.chatListeners.get(row.id)?.size && !view.busy && view.revision !== row.revision) void this.open(row.id, true);
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
  open(id: string, refresh = false): Promise<void> {
    if (!this.owner) return Promise.resolve();
    const existing = this.loads.get(id); if (existing) return existing;
    const view = this.view(id), chat = this.chats.get(id);
    if (view.busy && this.pending.has(id) && !refresh) return Promise.resolve();
    if (!refresh && view.messages.length && view.revision === chat?.revision && !view.busy) return Promise.resolve();
    const signal = this.controller.signal, cache = this.cache!;
    this.setView(id, { loading: true });
    const operation = (async () => {
      try {
        if (!view.messages.length && !refresh) {
          const cached = await cache.messages(id).catch(() => []);
          if (this.alive(signal) && cached.length) this.setView(id, { messages: cached, before: cached[0].sequence > 1 ? cached[0].sequence : null });
        }
        const page = await api.getTurn(id, signal); if (!this.alive(signal)) return;
        await this.applyPage(page);
        if (this.alive(signal) && page.turn?.state === 'RUNNING' && !refresh) this.poll(id);
      } catch (error) { if (this.alive(signal)) this.setView(id, { loading: false, busy: false, error: this.error(error) }); }
    })();
    this.loads.set(id, operation);
    void operation.finally(() => { if (this.loads.get(id) === operation) this.loads.delete(id); });
    return operation;
  }
  private async applyPage(page: MessagePage, older = false) {
    const signal = this.controller.signal, cache = this.cache!;
    const id = page.conversation.id, view = this.view(id);
    if (this.deleted.has(id)) return;
    if (page.conversation.revision < view.revision) return;
    this.mergeChats([page.conversation]);
    const values = new Map<number, StoredMessage>();
    if (older || page.incremental) view.messages.forEach(message => values.set(message.sequence, message));
    page.items.forEach(message => values.set(message.sequence, message));
    const items = [...values.values()].sort((a,b) => a.sequence - b.sequence);
    const messages = older ? items.slice(0, 200) : items.slice(-200);
    this.setView(id, { messages, loading: false, busy: page.turn?.state === 'RUNNING',
      error: page.turn?.state === 'FAILED' ? page.turn.error : null, turn: page.turn ?? view.turn,
      before: page.incremental ? (messages[0]?.sequence > 1 ? messages[0].sequence : null) : page.has_more ? messages[0]?.sequence ?? null : null,
      olderWindow: older && items.length > 200 || older && view.olderWindow,
      revision: page.conversation.revision });
    this.publish();
    await this.persist(() => cache.apply([page.conversation], page.items, []));
    if (!this.alive(signal)) return;
    if (page.turn && page.turn.state !== 'RUNNING') {
      this.pending.delete(id); await this.persist(() => cache.pending(null, id));
    }
  }
  async older(id: string) {
    const view = this.view(id); if (!view.before || view.loading) return;
    const signal = this.controller.signal;
    this.setView(id, { loading: true });
    try { const page = await api.getMessages(id, view.before, signal); if (this.alive(signal)) await this.applyPage({ ...page, turn: view.turn }, true); }
    catch (error) { if (this.alive(signal)) this.setView(id, { loading: false, error: this.error(error) }); }
  }
  async send(id: string, content: string, retrieval: ChatSelection, retry = false) {
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
      body = { conversation_id: id, client_turn_id: view.turn.id, expected_revision: view.revision, content: message.content, retrieval: view.turn.selection };
    }
    body ??= { conversation_id: id, client_turn_id: crypto.randomUUID(), expected_revision: this.chats.get(id)?.revision ?? 0, content, retrieval };
    body = { ...body, retry };
    this.pending.set(id, body);
    this.setView(id, { busy: true, error: null, unsent: null });
    await this.persist(() => cache.pending(body!, id));
    if (!this.alive(signal)) return;
    const optimistic: StoredMessage = { id: body.client_turn_id, conversation_id: id, sequence: (this.chats.get(id)?.message_count ?? 0) + 1,
      role: 'user', content: body.content, created_at: new Date().toISOString() };
    this.setView(id, { busy: true, error: null, olderWindow: false, messages: retry ? view.messages : [...view.messages, optimistic].slice(-200) });
    try {
      const page = await api.sendTurn(body, signal); if (!this.alive(signal)) return;
      await this.applyPage(page);
      if (!this.alive(signal)) return;
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
        this.setView(id, { busy: false, error: 'Connection interrupted. Check the saved turn before retrying.' });
        void this.open(id, true);
      }
    }
  }
  private poll(id: string, attempt = 0) {
    if (this.pollers.has(id)) return;
    const signal = this.controller.signal;
    this.pollers.set(id, setTimeout(async () => {
      this.pollers.delete(id); if (!this.alive(signal)) return;
      await this.open(id, true);
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
      await this.persist(() => cache.apply([], [], [id])); this.channel?.postMessage('changed'); void this.sync(); return true;
    } catch (error) { if (this.alive(signal)) { this.list = { ...this.list, error: this.error(error) }; this.publish(); void this.sync(); } return false; }
  }
  private error(error: unknown) { return error instanceof Error ? error.message : 'Could not synchronize chats.'; }
  hasPending(id: string) { return this.pending.has(id); }
  clearUnsent(id: string) { this.setView(id, { unsent: null, error: null }); }
}
export const chatStore = new ChatStore();
export const useChatList = () => useSyncExternalStore(chatStore.subscribe, chatStore.snapshot);
export function useConversation(id: string) {
  return useSyncExternalStore(fn => chatStore.subscribeChat(id, fn), () => chatStore.view(id));
}
