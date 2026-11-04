import { useSyncExternalStore } from 'react';

const key = 'mentra.open-sources-in-panel.v1';
function read(fallback = true) {
  try { return localStorage.getItem(key) !== 'off'; } catch { return fallback; }
}
let enabled = read();
const listeners = new Set<() => void>();
function update(next: boolean) {
  if (enabled === next) return;
  enabled = next;
  listeners.forEach(listener => listener());
}
function sync(event: StorageEvent) {
  if (event.key === key || event.key === null) update(event.newValue !== 'off');
}
function subscribe(listener: () => void) {
  if (!listeners.size) {
    enabled = read(enabled);
    window.addEventListener('storage', sync);
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (!listeners.size) window.removeEventListener('storage', sync);
  };
}
export function useOpenSourcesInMentra() {
  return useSyncExternalStore(subscribe, () => enabled, () => true);
}
export function setOpenSourcesInMentra(value: boolean) {
  update(value);
  try { localStorage.setItem(key, value ? 'on' : 'off'); } catch { /* Optional storage. */ }
}
export const openSourcesInMentra = () => read(enabled);
