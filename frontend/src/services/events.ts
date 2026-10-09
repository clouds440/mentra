import { apiRequest } from './api';
import type { EventDraft, EventRecord, EventPage, EventOutcome, EventStatus, TemporalPreview } from '../types/events';
const base = '/api/v1/events';
function details(value: EventDraft): EventDraft {
  const { title, description, kind, context_id, timezone, local_date, starts_at, ends_at, reminder } = value;
  return { title, description, kind, context_id, timezone, local_date, starts_at, ends_at, reminder };
}
export const events = {
  list: (params: URLSearchParams, signal: AbortSignal) => apiRequest<EventPage>(`${base}?${params}`, { signal }),
  detail: (id: string, signal: AbortSignal) => apiRequest<EventRecord>(`${base}/${encodeURIComponent(id)}`, { signal }),
  preview: (body: unknown, signal: AbortSignal) => apiRequest<TemporalPreview>(`${base}/temporal-preview`, { method: 'POST', body: JSON.stringify(body), signal }),
  save: (draft: EventDraft, operation: string, signal: AbortSignal, current?: EventRecord) => apiRequest<EventOutcome>(current ? `${base}/${current.id}` : base, { method: current ? 'PATCH' : 'POST', signal, body: JSON.stringify(current ? { expected_revision: current.revision, client_request_id: operation, details: details(draft) } : { ...details(draft), client_request_id: operation }) }),
  status: (item: EventRecord, status: EventStatus, operation: string, signal: AbortSignal) => apiRequest<EventOutcome>(`${base}/${item.id}`, { method: 'PATCH', signal, body: JSON.stringify({ expected_revision: item.revision, client_request_id: operation, status }) }),
  remove: (item: EventRecord, operation: string, signal: AbortSignal) => apiRequest<EventOutcome>(`${base}/${item.id}?expected_revision=${item.revision}&client_request_id=${operation}`, { method: 'DELETE', signal }),
};
