import type { SourceReference, ChatSelection } from './rag';
import type { HistoryReference, MemoryReference } from './memories';
export interface ToolWarning {
  tool_name: string; code: string; message: string;
  task_impact: string; effect_certainty: string;
}
export interface ResponseOutcome {
  version: number;
  state: 'completed' | 'awaiting_input' | 'in_progress' | 'partial' | 'failed' | 'paused';
  retryable: boolean;
  reason_code?: string | null;
  tasks?: { id: string; job_id?: string; job_kind?: string; job_revision?: number | null }[];
  control_action?: { kind: 'generation_retry' | 'generation_resume' | 'grading_retry'; id: string; revision: number } | null;
}
export interface ChatMessageData {
  response_outcome?: ResponseOutcome;
  timezone?: string;
  web_sources?: import('./webSearch').WebSource[];
  web_citations?: string[];
  web_searches?: import('./webSearch').WebSearchRecord[];
  tool_warnings?: ToolWarning[];
  interactions?: import('./interactions').InteractionCardData[];
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
  assessment_cards?: (import('./assessments').ChatAssessmentCardData | import('./assessments').GenerationCardData)[];
  event_references?: import('./events').EventRecord[];
}
