import { apiRequest } from './api';
import type { Conversation, MessagePage, PendingTurn, SyncPage } from '../types/conversations';

const base = '/api/v1/conversations';
export const syncChats = (cursor: number | null, active?: string, signal?: AbortSignal) => {
  const query = new URLSearchParams();
  if (cursor !== null) query.set('cursor', String(cursor));
  if (active) query.set('active', active);
  return apiRequest<SyncPage>(`${base}/sync?${query}`, { signal });
};
export const listChats = (cursor: string, signal?: AbortSignal) => apiRequest<{ items: Conversation[]; next_cursor: string | null }>(`${base}?cursor=${encodeURIComponent(cursor)}`, { signal });
export const getMessages = (id: string, before?: number, signal?: AbortSignal) => apiRequest<MessagePage>(`${base}/${id}/messages${before ? `?before=${before}` : ''}`, { signal });
export const getTurn = (id: string, signal?: AbortSignal) => apiRequest<MessagePage>(`${base}/${id}/status`, { signal });
export const sendTurn = (body: PendingTurn, signal?: AbortSignal) => apiRequest<MessagePage>(`${base}/turns`, { method: 'POST', body: JSON.stringify(body), signal });
export const renameChat = (chat: Conversation, title: string, signal?: AbortSignal) => apiRequest<Conversation>(`${base}/${chat.id}`, { method: 'PATCH', body: JSON.stringify({ expected_revision: chat.revision, title }), signal });
export const deleteChat = (chat: Conversation, signal?: AbortSignal) => apiRequest<Conversation>(`${base}/${chat.id}?expected_revision=${chat.revision}`, { method: 'DELETE', signal });
