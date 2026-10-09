import { apiRequest } from './api';
import type { EventProposal, EventDraft } from '../types/events';
const base = '/api/v1/event-proposals';
export const eventProposals = {
  list: (signal: AbortSignal, conversation?: string) => apiRequest<EventProposal[]>(`${base}${conversation ? `?conversation_id=${encodeURIComponent(conversation)}` : ''}`, { signal }),
  detail: (id: string, signal: AbortSignal) => apiRequest<EventProposal>(`${base}/${id}`, { signal }),
  decide: (proposal: EventProposal, decision: 'approve' | 'dismiss', signal: AbortSignal, details?: EventDraft) => apiRequest<EventProposal>(`${base}/${proposal.id}/decisions`, { method: 'POST', signal, body: JSON.stringify({ expected_revision: proposal.revision, decision, ...(details ? { details } : {}) }) }),
};
