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
  timezone?: string;
  interaction_response?: import('./interactions').InteractionResponse;
  conversation_id: string; client_turn_id: string; expected_revision: number;
  content: string; retrieval: ChatSelection; retry?: boolean;
  attachment_ids?: string[];
  resume_from?: string;
}
export interface Turn {
  can_resume?: boolean; can_retry?: boolean; can_stop?: boolean; resume_until?: string | null;
  attempt: number;
  id: string; state: 'RUNNING' | 'SUCCEEDED' | 'FAILED'; error: string | null;
  selection: ChatSelection; user_sequence: number;
  attachment_ids?: string[];
}
export interface MessagePage {
  continued_turn_id?: string;
  conversation: Conversation; items: StoredMessage[]; has_more: boolean; next_cursor: number | null;
  turn?: Turn | null;
  incremental?: boolean;
}
export interface SyncPage {
  reset: boolean; cursor: number; has_more: boolean;
  conversations: Conversation[]; deleted_ids: string[]; active?: MessagePage; list_cursor?: string | null;
}
export interface ChatSearchHit {
  conversation_id: string; title: string; matched_message_id: string; sequence: number;
  role: 'user' | 'assistant'; snippet: string; created_at: string; matched_in: 'message' | 'title';
}
export interface ChatSearchPage { items: ChatSearchHit[]; next_offset: number | null; truncated: boolean }
export interface SavedExchange {
  conversation_id: string; title: string; matched_message_id: string;
  messages: { id: string; role: 'user' | 'assistant'; content: string; created_at: string }[];
}
