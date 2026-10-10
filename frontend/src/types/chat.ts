import type { SourceReference, ChatSelection } from './rag';
import type { HistoryReference, MemoryReference } from './memories';
export interface ChatMessageData {
  attachments?: import('../services/chatAttachments').ChatAttachment[];
  conversation_id?: string;
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
  event_proposals?: import('./events').EventProposal[];
  assessment_cards?: import('./assessments').ChatAssessmentCardData[];
  event_references?: import('./events').EventRecord[];
}

export type ChatTurn = Pick<ChatMessageData, 'role' | 'content'>;

export interface ChatResponse {
  role: 'assistant';
  assessment_cards?: import('./assessments').ChatAssessmentCardData[];
  content: string;
  sources?: SourceReference[];
  citations?: string[];
  retrieval_status?: string;
  retrieval_warning?: string | null;
  retrieval_scope?: ChatSelection | null;
  history_references?: HistoryReference[];
  memory_references?: MemoryReference[];
}
