export interface UserMemory {
  id: string;
  content: string;
  category: 'preference' | 'fact' | 'goal';
  status: 'active' | 'pending' | 'conflict';
  origin: 'manual' | 'ai';
  revision: number;
  conflicts: { memory_id: string; revision: number; content: string }[];
  pinned: boolean;
  stale: boolean;
  created_at: string;
  updated_at: string;
  confirmed_at: string | null;
  expires_at: string | null;
  evidence?: MemoryEvidence[];
}
export interface MemoryEvidence {
  id: string;
  quote: string;
  source_date: string;
  source_deleted: boolean;
  conversation_id: string | null;
  message_id: string | null;
  explicit_consent: boolean;
}
export interface MemoryPage { items: UserMemory[]; next_cursor: string | null }
export interface MemoryPreferences { automatic_memory: boolean; revision: number; active_limit?: number; pending_limit?: number; manual_limit?: number }
export interface HistoryReference { token: string; conversation_id: string; title: string; sequence: number }
export interface MemoryReference { token: string; memory_id: string; revision: number }
export interface HistoryWindow { title: string; conversation_id: string; messages: { id: string; role: 'user' | 'assistant'; content: string; created_at: string; exchange_status?: string }[] }
