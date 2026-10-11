import type { SourceReference, ChatSelection } from './rag';
import type { HistoryReference, MemoryReference } from './memories';
export interface ToolWarning {
  tool_name: string; code: string; message: string;
  task_impact: string; effect_certainty: string;
}
export interface ChatMessageData {
  web_sources?: import('./webSearch').WebSource[];
  web_citations?: string[];
  web_searches?: import('./webSearch').WebSearchRecord[];
  tool_warnings?: ToolWarning[];
  interactions?: import('./interactions').ChoiceCardData[];
  interaction_response?: import('./interactions').InteractionResponse;
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
  web_sources?: import('./webSearch').WebSource[];
  web_citations?: string[];
  web_searches?: import('./webSearch').WebSearchRecord[];
  tool_warnings?: ToolWarning[];
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
