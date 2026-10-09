import { apiRequest } from './api';
import type { UploadResult } from '../types/rag';

export interface ChatAttachment { id: string; filename: string; size_bytes: number }
export interface AttachmentDetail extends ChatAttachment {
  ready: boolean; error: string | null; warnings: string[]; library_result: UploadResult | null;
}
export const uploadChatAttachment = (file: File, signal?: AbortSignal) => {
  const body = new FormData(); body.append('file', file);
  return apiRequest<ChatAttachment>('/api/v1/chat-attachments', { method: 'POST', body, signal });
};
export const removeChatAttachment = (id: string) => apiRequest<void>(`/api/v1/chat-attachments/${id}`, { method: 'DELETE' });
export const getChatAttachment = (id: string, conversationId: string, signal?: AbortSignal) =>
  apiRequest<AttachmentDetail>(`/api/v1/chat-attachments/${id}?conversation_id=${conversationId}`, { signal });
export const saveChatAttachment = (id: string, conversationId: string, contextIds: string[], signal?: AbortSignal) =>
  apiRequest<UploadResult>(`/api/v1/chat-attachments/${id}/library`, { method: 'POST', body: JSON.stringify({ conversation_id: conversationId, context_ids: contextIds }), signal });
