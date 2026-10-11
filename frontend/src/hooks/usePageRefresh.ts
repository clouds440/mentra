import { useEffect, useRef } from 'react';
import { invalidatePageCache } from '../services/pageCache';

// Keep mounted pages current as well as pages revisited after the cache expires.
export function usePageRefresh(refresh: () => void, enabled = true) {
  const latest = useRef(refresh);
  latest.current = refresh;
  useEffect(() => {
    if (!enabled) return;
    const update = () => {
      if (document.visibilityState === 'visible' && navigator.onLine) latest.current();
    };
    const timer = setInterval(update, 60_000);
    window.addEventListener('focus', update);
    window.addEventListener('online', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', update);
      window.removeEventListener('online', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, [enabled]);
}

export function refreshPage(refresh: () => void) {
  invalidatePageCache();
  refresh();
}
