export interface WebsiteIdentity { domain: string; favicon_url: string }
export interface WebSource extends WebsiteIdentity {
  token: string; url: string; title: string; excerpt: string; searched_at: string;
  published_date?: string | null; published_at?: string | null;
  updated_date?: string | null; updated_at?: string | null; data_as_of?: string | null;
  source_date_status: 'available' | 'missing' | 'invalid' | 'future';
}
export interface WebSearchRecord {
  outcome: 'ok' | 'partial' | 'no_results' | 'unavailable' | 'quota_exhausted' | 'rate_limited' | 'timeout' | 'invalid_input' | 'budget_exhausted' | 'disabled';
  reason?: string | null; current_date: string; current_datetime: string; reference_timezone: string;
  searched_at?: string | null; delivered_at: string; reused_within_turn: boolean; website?: string | null;
  cache_hit?: boolean; cache_expires_at?: string | null;
}
