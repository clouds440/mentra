import { apiRequest } from './api';
import type { NotificationItem, NotificationPage, NotificationPreferences } from '../types/notifications';
const base = '/api/v1/notifications';
export const notifications = {
  list: (signal: AbortSignal, before?: string, unread = false, limit = 30) => apiRequest<NotificationPage>(`${base}?unread=${unread}&limit=${limit}${before ? `&before=${encodeURIComponent(before)}` : ''}`, { signal }),
  edit: (item: NotificationItem, action: 'read' | 'dismiss', signal: AbortSignal) => apiRequest<NotificationItem>(`${base}/${item.id}`, { method: 'PATCH', signal, body: JSON.stringify({ expected_revision: item.revision, action }) }),
  preferences: (signal: AbortSignal) => apiRequest<NotificationPreferences>(`${base}/preferences`, { signal }),
  savePreferences: (value: NotificationPreferences, signal: AbortSignal) => apiRequest<NotificationPreferences>(`${base}/preferences`, { method: 'PATCH', signal, body: JSON.stringify({ enabled: value.enabled, disabled_kinds: value.disabled_kinds, expected_revision: value.revision }) }),
};
export function notificationChanged() { window.dispatchEvent(new Event('mentra:notifications-changed')); }
