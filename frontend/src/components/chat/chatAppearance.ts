import { useSyncExternalStore } from 'react';

export type ChatFontSize = 'small' | 'medium' | 'large';
const key = 'mentra-chat-font-size';
const valid = (value: unknown): ChatFontSize => value === 'small' || value === 'large' ? value : 'medium';
function read(fallback: ChatFontSize = 'medium') { try { return valid(localStorage.getItem(key)); } catch { return fallback; } }
let current = read();
const listeners = new Set<() => void>();
function publish(value: unknown) { const next = valid(value); if (next === current) return; current = next; listeners.forEach(listener => listener()); }
function subscribe(listener: () => void) {
  if (!listeners.size) current = read(current);
  listeners.add(listener);
  const sync = (event: StorageEvent) => { if (event.key === key || event.key === null) publish(event.key === null ? null : event.newValue); };
  window.addEventListener('storage', sync);
  return () => { listeners.delete(listener); window.removeEventListener('storage', sync); };
}
export function useChatFontSize() { return useSyncExternalStore(subscribe, () => current, () => 'medium' as const); }
export function setChatFontSize(value: ChatFontSize) {
  publish(value);
  try { localStorage.setItem(key, current); } catch { /* Session appearance works when storage is blocked. */ }
}
