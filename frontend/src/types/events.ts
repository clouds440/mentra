export type EventKind = 'quiz' | 'exam' | 'assignment' | 'deadline' | 'study' | 'other';
export type EventStatus = 'scheduled' | 'completed' | 'cancelled';
export interface EventDraft {
  title: string; description: string; kind: EventKind; context_id: string | null;
  timezone: string; local_date: string | null; starts_at: string | null; ends_at: string | null;
  reminder: { mode: 'default' | 'disabled' | 'at'; at?: string | null };
}
export interface EventRecord extends EventDraft {
  id: string; status: EventStatus; origin: 'manual' | 'ai'; revision: number;
  bucket: string; reminder_state: string; reminder_due_at: string | null;
  evidence?: { quote: string; source_date: string; source_timezone: string; source_deleted: boolean; conversation_id: string | null }[];
}
export interface EventPage { items: EventRecord[]; next_cursor: string | null; has_more: boolean; sync_revision: number }
export interface EventOutcome { outcome: string; event: EventRecord | null; event_id: string }
export interface TemporalChoice { starts_at: string | null; ends_at: string | null; reminder_due_at: string | null; reminder_state: string }
export interface TemporalPreview { choices: TemporalChoice[]; requires_choice: boolean; field_errors: { field: string; message: string }[] }
export interface EventProposal {
  id: string; revision: number; state: 'pending' | 'deciding' | 'approved' | 'dismissed' | 'cancelled' | 'expired';
  action: 'create' | 'edit' | 'status'; candidate: Partial<EventDraft> | null;
  target_id: string | null; target_revision: number | null; status: EventStatus | null;
  uncertainty: string; quote: string; source_date: string; conversation_id: string;
  expires_at: string; event_id: string | null; workflow_version: string;
}
