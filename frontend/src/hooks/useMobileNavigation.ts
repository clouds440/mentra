import { useLayoutEffect, useRef, useState, type RefObject } from 'react';

export function useMobileNavigation(panel: RefObject<HTMLElement>, open: boolean, dismiss: () => void) {
  const [desktop, setDesktop] = useState(() => matchMedia('(min-width: 1024px)').matches);
  const close = useRef(dismiss); close.current = dismiss;
  useLayoutEffect(() => {
    const media = matchMedia('(min-width: 1024px)');
    const update = () => { setDesktop(media.matches); if (media.matches) close.current(); };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useLayoutEffect(() => {
    const navigation = panel.current;
    if (!navigation) return;
    navigation.inert = !desktop && !open;
    if (desktop || !open) return;
    const content = document.getElementById('workspace-content');
    const previous = document.querySelector<HTMLElement>('#workspace-content button[aria-label="Open navigation menu"]') ?? document.activeElement as HTMLElement | null;
    const priorInert = content?.inert ?? false;
    if (content) content.inert = true;
    const focusable = () => Array.from(navigation.querySelectorAll<HTMLElement>('a[href],button:not(:disabled),input:not(:disabled),[tabindex="0"]')).filter(element => element.getClientRects().length > 0);
    const frame = requestAnimationFrame(() => focusable()[0]?.focus());
    const keydown = (event: KeyboardEvent) => {
      // Native top-layer dialogs own focus and Escape while above navigation.
      if (document.querySelector('dialog[open]')) return;
      if (event.key === 'Escape' && !event.defaultPrevented && !navigation.querySelector('#sidebar-account-panel, [role="listbox"]')) { event.preventDefault(); close.current(); }
      if (event.key !== 'Tab' || event.defaultPrevented) return;
      const targets = focusable(); const first = targets[0], last = targets[targets.length - 1];
      if (!first) { event.preventDefault(); navigation.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || !navigation.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !navigation.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', keydown);
    return () => {
      cancelAnimationFrame(frame); document.removeEventListener('keydown', keydown);
      if (content) content.inert = priorInert;
      requestAnimationFrame(() => {
        // A nested popover may restore its anchor during the same Escape event.
        if (navigation.inert && previous?.isConnected && !previous.closest('[inert]') && previous.getClientRects().length) previous.focus();
      });
    };
  }, [panel, desktop, open]);
  return desktop;
}
