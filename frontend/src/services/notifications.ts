import { apiRequest, apiEvents } from './api';
import { invalidatePageCache } from './pageCache';
import type { NotificationItem, NotificationPage, NotificationPreferences } from '../types/notifications';
const base = '/api/v1/notifications';
export const notifications = {
  unread: (signal: AbortSignal) => apiRequest<{ unread_count: number; sync_revision: number }>(`${base}/unread`, { signal, cache: 'no-store' }),
  list: (signal: AbortSignal, before?: string, unread = false, limit = 30) => apiRequest<NotificationPage>(`${base}?unread=${unread}&limit=${limit}${before ? `&before=${encodeURIComponent(before)}` : ''}`, { signal }),
  edit: (item: NotificationItem, action: 'read' | 'dismiss', signal: AbortSignal) => apiRequest<NotificationItem>(`${base}/${item.id}`, { method: 'PATCH', signal, body: JSON.stringify({ expected_revision: item.revision, action }) }),
  preferences: (signal: AbortSignal) => apiRequest<NotificationPreferences>(`${base}/preferences`, { signal }),
  savePreferences: (value: NotificationPreferences, signal: AbortSignal) => apiRequest<NotificationPreferences>(`${base}/preferences`, { method: 'PATCH', signal, body: JSON.stringify({ enabled: value.enabled, disabled_kinds: value.disabled_kinds, expected_revision: value.revision }) }),
};
export function notificationChanged() { window.dispatchEvent(new Event('mentra:notifications-changed')); }

type Snapshot = { unread_count: number; sync_revision: number };
const streams = new Map<string, { controller: AbortController; listeners: Set<(value: Snapshot) => void> }>();
export function watchNotifications(owner: string, listener: (value: Snapshot) => void) {
  let stream = streams.get(owner);
  if (!stream) {
    stream = { controller: new AbortController(), listeners: new Set() };
    streams.set(owner, stream);
    const current = stream;
    void (async () => {
      let revision: number | undefined, failures = 0;
      while (!current.controller.signal.aborted) {
        try {
          await apiEvents(`${base}/changes`, current.controller.signal, (name, data) => {
            if (name !== 'notifications' || current.controller.signal.aborted) return;
            const value = data as Snapshot;
            if (!Number.isSafeInteger(value.sync_revision) || !Number.isSafeInteger(value.unread_count)) return;
            if (revision !== undefined && revision !== value.sync_revision) invalidatePageCache(['notifications'], true);
            revision = value.sync_revision; failures = 0;
            current.listeners.forEach(receive => receive(value));
          });
        } catch { failures = Math.min(5, failures + 1); }
        if (current.controller.signal.aborted) break;
        await new Promise<void>(resolve => {
          const cancel = () => { clearTimeout(timer); resolve(); };
          const timer = setTimeout(() => { current.controller.signal.removeEventListener('abort', cancel); resolve(); }, 1000 * 2 ** failures);
          current.controller.signal.addEventListener('abort', cancel, { once: true });
        });
      }
    })();
  }
  stream.listeners.add(listener);
  return () => {
    stream!.listeners.delete(listener);
    if (!stream!.listeners.size) { stream!.controller.abort(); streams.delete(owner); }
  };
}
