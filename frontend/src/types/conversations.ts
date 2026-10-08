import type { ChatMessageData } from './chat';
import type { ChatSelection } from './rag';

export interface Conversation {
  id: string; title: string; revision: number; message_count: number;
  selection: ChatSelection; created_at: string; updated_at: string; deleted_at: string | null;
}
export interface StoredMessage extends ChatMessageData {
  conversation_id: string; sequence: number; created_at: string;
}
export interface PendingTurn {
  conversation_id: string; client_turn_id: string; expected_revision: number;
  content: string; retrieval: ChatSelection; retry?: boolean;
}
export interface Turn {
  id: string; state: 'RUNNING' | 'SUCCEEDED' | 'FAILED'; error: string | null;
  selection: ChatSelection; user_sequence: number;
}
export interface MessagePage {
  conversation: Conversation; items: StoredMessage[]; has_more: boolean; next_cursor: number | null;
  turn?: Turn | null;
  incremental?: boolean;
}
export interface SyncPage {
  reset: boolean; cursor: number; has_more: boolean;
  conversations: Conversation[]; deleted_ids: string[]; active?: MessagePage; list_cursor?: string | null;
}
