import { apiRequest } from './api';
import type { HistoryWindow, MemoryPage, MemoryPreferences, UserMemory } from '../types/memories';

const base = '/api/v1/memories';
export const memoryApi = {
  list: (query: string, status: string, cursor?: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ query });
    if (status) params.set('status', status);
    if (cursor) params.set('cursor', cursor);
    return apiRequest<MemoryPage>(`${base}?${params}`, { signal });
  },
  preferences: (signal?: AbortSignal) => apiRequest<MemoryPreferences>(`${base}/preferences`, { signal }),
  configure: (value: boolean, revision: number) => apiRequest<MemoryPreferences>(`${base}/preferences`, { method: 'PATCH', body: JSON.stringify({ automatic_memory: value, expected_revision: revision }) }),
  detail: (id: string, signal?: AbortSignal) => apiRequest<UserMemory>(`${base}/${id}`, { signal }),
  create: (content: string, category: string, clientRequestId: string) => apiRequest<{ outcome: string; memory: UserMemory }>(base, { method: 'POST', body: JSON.stringify({ content, category, client_request_id: clientRequestId }) }),
  edit: (memory: UserMemory, fields: Record<string, unknown>) => apiRequest<UserMemory>(`${base}/${memory.id}`, { method: 'PATCH', body: JSON.stringify({ ...fields, expected_revision: memory.revision }) }),
  remove: (memory: UserMemory) => apiRequest<{ deleted: boolean }>(`${base}/${memory.id}?expected_revision=${memory.revision}`, { method: 'DELETE' }),
  history: (id: string, sequence: number, signal?: AbortSignal) => apiRequest<HistoryWindow>(`${base}/history/${id}?sequence=${sequence}`, { signal }),
};
