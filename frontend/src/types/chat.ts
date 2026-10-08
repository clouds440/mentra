import type { SourceReference, ChatSelection } from './rag';
export interface ChatMessageData {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceReference[];
  citations?: string[];
  retrieval_status?: string;
  retrieval_warning?: string | null;
  retrieval_scope?: ChatSelection | null;
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
}
