import { useEffect, useRef } from 'react';
import { invalidatePageCache, subscribePageChanges, type PageScope } from '../services/pageCache';

// Settled pages react to relevant writes, never clocks, focus or connectivity.
export function usePageRefresh(refresh: () => void, enabled = true, scopes?: readonly PageScope[]) {
  const latest = useRef({ refresh, enabled, scopes });
  latest.current = { refresh, enabled, scopes };
  useEffect(() => {
    let frame: number | undefined;
    const unsubscribe = subscribePageChanges(changed => {
      const current = latest.current;
      if (changed && current.scopes && !changed.some(scope => current.scopes!.includes(scope))) return;
      if (frame !== undefined) return;
      frame = requestAnimationFrame(() => {
        frame = undefined;
        if (latest.current.enabled) latest.current.refresh();
      });
    });
    return () => { unsubscribe(); if (frame !== undefined) cancelAnimationFrame(frame); };
  }, []);
}

// Only unfinished user-started work needs polling; callers keep content mounted.
export function usePendingWork(refresh: () => void, enabled: boolean) {
  const latest = useRef(refresh); latest.current = refresh;
  useEffect(() => {
    if (!enabled) return;
    const timer = setInterval(() => latest.current(), 3000);
    return () => clearInterval(timer);
  }, [enabled]);
}

export function refreshPage(refresh: () => void) {
  invalidatePageCache();
  refresh();
}
