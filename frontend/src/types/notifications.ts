export interface NotificationItem {
  id: string;
  kind: string;
  title: string;
  body: string;
  target_kind: 'event' | 'assessment' | 'none';
  target_id: string | null;
  created_at: string;
  read_at: string | null;
  dismissed_at: string | null;
  revision: number;
}
export interface NotificationPage {
  items: NotificationItem[];
  next_cursor: string | null;
  unread_count: number;
  sync_revision: number;
}
export interface NotificationPreferences {
  enabled: boolean;
  disabled_kinds: string[];
  revision: number;
}
