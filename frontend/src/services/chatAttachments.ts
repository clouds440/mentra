import { apiRequest } from './api';
import { uploadFile, downloadFile } from './files';
import type { UploadResult } from '../types/rag';

export interface ChatAttachment { id: string; filename: string; size_bytes: number }
export interface AttachmentDetail extends ChatAttachment {
  ready: boolean; error: string | null; warnings: string[]; library_result: UploadResult | null;
}
export const uploadChatAttachment = async (file: File, signal?: AbortSignal) => {
  const stored = await uploadFile(file, file.name, 'chat', signal);
  return apiRequest<ChatAttachment>('/api/v1/chat-attachments', { method: 'POST', body: JSON.stringify({ file_id: stored.id }), signal });
};
export const removeChatAttachment = (id: string) => apiRequest<void>(`/api/v1/chat-attachments/${id}`, { method: 'DELETE' });
export const getChatAttachmentSource = (id: string, conversationId: string, signal?: AbortSignal) => downloadFile(`/api/v1/chat-attachments/${id}/source?conversation_id=${encodeURIComponent(conversationId)}`, signal);
export const getChatAttachment = (id: string, conversationId: string, signal?: AbortSignal) =>
  apiRequest<AttachmentDetail>(`/api/v1/chat-attachments/${id}?conversation_id=${conversationId}`, { signal });
export const saveChatAttachment = (id: string, conversationId: string, contextIds: string[], signal?: AbortSignal) =>
  apiRequest<UploadResult>(`/api/v1/chat-attachments/${id}/library`, { method: 'POST', body: JSON.stringify({ conversation_id: conversationId, context_ids: contextIds }), signal });
