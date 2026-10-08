import { openDB, deleteDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { Conversation, PendingTurn, StoredMessage } from '../types/conversations';

interface CacheSchema extends DBSchema {
  conversations: { key: string; value: Conversation; indexes: { updated: string } };
  messages: { key: string; value: StoredMessage; indexes: { conversation: string; order: [string, number] } };
  pending: { key: string; value: PendingTurn };
  deleted: { key: string; value: { id: string; at: number }; indexes: { at: number } };
  meta: { key: string; value: number | string | null };
}

export class ChatCache {
  private db: Promise<IDBPDatabase<CacheSchema> | null>;
  readonly name: string;
  constructor(owner: string) {
    this.name = `mentra-chat-v1-${owner}`;
    this.db = Promise.resolve().then(() => openDB<CacheSchema>(this.name, 2, {
      upgrade(db, previous) {
        if (previous < 1) {
        db.createObjectStore('conversations', { keyPath: 'id' }).createIndex('updated', 'updated_at');
        const messages = db.createObjectStore('messages', { keyPath: 'id' });
        messages.createIndex('conversation', 'conversation_id');
        messages.createIndex('order', ['conversation_id', 'sequence']);
        db.createObjectStore('pending', { keyPath: 'conversation_id' });
        db.createObjectStore('meta');
        }
        if (previous < 2) db.createObjectStore('deleted', { keyPath: 'id' }).createIndex('at', 'at');
      },
    })).then(db => { db.onversionchange = () => db.close(); return db; }).catch(() => null);
  }
  async hydrate() {
    const db = await this.db;
    if (!db) return { conversations: [], pending: [], cursor: null, listCursor: null };
    const tx = db.transaction(['conversations', 'pending', 'meta']);
    const [conversations, pending, cursor, listCursor] = await Promise.all([
      tx.objectStore('conversations').getAll(), tx.objectStore('pending').getAll(),
      tx.objectStore('meta').get('cursor'), tx.objectStore('meta').get('listCursor'),
    ]);
    return { conversations, pending, cursor: typeof cursor === 'number' ? cursor : null, listCursor: typeof listCursor === 'string' ? listCursor : null };
  }
  async messages(id: string) {
    const db = await this.db;
    if (!db) return [];
    const tx = db.transaction('messages');
    const result: StoredMessage[] = [];
    let cursor = await tx.store.index('order').openCursor(IDBKeyRange.bound([id, 0], [id, Number.MAX_SAFE_INTEGER]), 'prev');
    while (cursor && result.length < 200) { result.push(cursor.value); cursor = await cursor.continue(); }
    return result.reverse();
  }
  async apply(conversations: Conversation[], messages: StoredMessage[], removed: string[], cursor?: number, listCursor?: string | null, reset = false) {
    const db = await this.db;
    if (!db) return;
    const tx = db.transaction(['conversations', 'messages', 'pending', 'meta', 'deleted'], 'readwrite');
    if (reset) {
      await tx.objectStore('conversations').clear(); await tx.objectStore('messages').clear(); await tx.objectStore('meta').clear();
    }
    for (const chat of conversations) {
      if (await tx.objectStore('deleted').getKey(chat.id)) continue;
      const current = await tx.objectStore('conversations').get(chat.id);
      if (!current || current.revision < chat.revision) await tx.objectStore('conversations').put(chat);
    }
    // Server messages are immutable. Existing IDs need no rewrite on recovery or pagination.
    const blocked = new Set<string>();
    for (const id of new Set(messages.map(message => message.conversation_id))) if (await tx.objectStore('deleted').getKey(id)) blocked.add(id);
    for (const message of messages) if (!blocked.has(message.conversation_id) && !await tx.objectStore('messages').getKey(message.id)) await tx.objectStore('messages').put(message);
    for (const id of removed) {
      await tx.objectStore('deleted').put({ id, at: Date.now() });
      await tx.objectStore('conversations').delete(id); await tx.objectStore('pending').delete(id);
      let item = await tx.objectStore('messages').index('conversation').openCursor(id);
      while (item) { await item.delete(); item = await item.continue(); }
    }
    if (removed.length) {
      let excess = await tx.objectStore('deleted').count() - 10000;
      let tombstone = excess > 0 ? await tx.objectStore('deleted').index('at').openCursor() : null;
      while (tombstone && excess-- > 0) { await tombstone.delete(); tombstone = await tombstone.continue(); }
    }
    if (cursor !== undefined) {
      const previous = await tx.objectStore('meta').get('cursor');
      await tx.objectStore('meta').put(Math.max(typeof previous === 'number' ? previous : 0, cursor), 'cursor');
    }
    if (listCursor !== undefined) await tx.objectStore('meta').put(listCursor, 'listCursor');
    // Cache only 80 conversations and 200 messages each. Eviction never touches PostgreSQL.
    const evicted: string[] = [];
    let chatCursor = await tx.objectStore('conversations').count() > 80 ? await tx.objectStore('conversations').index('updated').openCursor(null, 'prev') : null;
    let count = 0;
    let oldestKept: Conversation | null = null;
    while (chatCursor) {
      if (++count > 80 && !await tx.objectStore('pending').get(chatCursor.primaryKey)) {
        evicted.push(chatCursor.primaryKey); await chatCursor.delete();
      } else oldestKept = chatCursor.value;
      chatCursor = await chatCursor.continue();
    }
    if (evicted.length && oldestKept) await tx.objectStore('meta').put(JSON.stringify([oldestKept.updated_at, oldestKept.id]), 'listCursor');
    const touched = new Set([...messages.map(message => message.conversation_id), ...evicted]);
    for (const id of touched) {
      const range = IDBKeyRange.bound([id, 0], [id, Number.MAX_SAFE_INTEGER]);
      const total = await tx.objectStore('messages').index('order').count(range);
      let remove = evicted.includes(id) ? total : Math.max(total - 200, 0);
      let item = remove ? await tx.objectStore('messages').index('order').openCursor(range) : null;
      while (item && remove-- > 0) { await item.delete(); item = await item.continue(); }
    }
    await tx.done;
  }
  async pending(value: PendingTurn | null, id: string) {
    const db = await this.db;
    if (!db) return;
    if (value) await db.put('pending', value); else await db.delete('pending', id);
  }
  async close(clear = false) {
    (await this.db)?.close();
    if (clear) await deleteDB(this.name);
  }
}
