import type { SourceReference, ChatSelection } from './rag';
import type { HistoryReference, MemoryReference } from './memories';
export interface ChatMessageData {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceReference[];
  citations?: string[];
  retrieval_status?: string;
  retrieval_warning?: string | null;
  retrieval_scope?: ChatSelection | null;
  history_references?: HistoryReference[];
  memory_references?: MemoryReference[];
}

export type ChatTurn = Pick<ChatMessageData, 'role' | 'content'>;

export interface ChatResponse {
  role: 'assistant';
  content: string;
  sources?: SourceReference[];
  citations?: string[];
  retrieval_status?: string;
  retrieval_warning?: string | null;
  retrieval_scope?: ChatSelection | null;
  history_references?: HistoryReference[];
  memory_references?: MemoryReference[];
}
