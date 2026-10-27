import { useSyncExternalStore } from 'react';

const listeners = new Set<() => void>();
let observer: MutationObserver | undefined;
const snapshot = () => document.documentElement.dataset.theme ?? 'light';
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!observer) {
    observer = new MutationObserver(() => listeners.forEach(notify => notify()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  }
  return () => { listeners.delete(listener); if (!listeners.size) { observer?.disconnect(); observer = undefined; } };
}
/** One shared observer, only for components that need the resolved palette in JS. */
export function useResolvedTheme() { return useSyncExternalStore(subscribe, snapshot, () => 'light'); }
