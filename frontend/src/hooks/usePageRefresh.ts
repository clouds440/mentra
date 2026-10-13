import { useEffect, useRef } from 'react';
import { invalidatePageCache } from '../services/pageCache';

// Keep mounted pages current as well as pages revisited after the cache expires.
export function usePageRefresh(refresh: () => void, enabled = true, interval = 60_000) {
  const latest = useRef(refresh);
  latest.current = refresh;
  useEffect(() => {
    if (!enabled) return;
    let frame: number | undefined;
    const update = () => {
      if (document.visibilityState !== 'visible' || !navigator.onLine || frame !== undefined) return;
      frame = requestAnimationFrame(() => { frame = undefined; latest.current(); });
    };
    const timer = setInterval(update, interval);
    window.addEventListener('focus', update);
    window.addEventListener('online', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      clearInterval(timer);
      if (frame !== undefined) cancelAnimationFrame(frame);
      window.removeEventListener('focus', update);
      window.removeEventListener('online', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, [enabled, interval]);
}

export function refreshPage(refresh: () => void) {
  invalidatePageCache();
  refresh();
}
