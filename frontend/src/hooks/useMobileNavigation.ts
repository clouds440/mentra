import { useLayoutEffect, useRef, useState, type RefObject } from 'react';

const navigation = { desktopQuery: '(min-width: 1024px)', inertIds: ['workspace-content'],
  closeOnDesktop: true, opener: '#workspace-content button[aria-label="Open navigation menu"]', fallbackFocus: '#workspace-main' };

export function useMobileNavigation(panel: RefObject<HTMLElement | null>, open: boolean, dismiss: () => void, options = navigation) {
  const [desktop, setDesktop] = useState(() => matchMedia(options.desktopQuery).matches);
  const close = useRef(dismiss); close.current = dismiss;
  useLayoutEffect(() => {
    const media = matchMedia(options.desktopQuery);
    const update = () => { setDesktop(media.matches); if (media.matches && options.closeOnDesktop) close.current(); };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [options]);
  useLayoutEffect(() => {
    const navigation = panel.current;
    if (!navigation) return;
    navigation.inert = !desktop && !open;
    if (desktop || !open) return;
    const previous = (options.opener && document.querySelector<HTMLElement>(options.opener)) || document.activeElement as HTMLElement | null;
    const background = options.inertIds.flatMap(id => {
      const element = document.getElementById(id);
      return element ? [{ element, inert: element.inert }] : [];
    });
    background.forEach(({ element }) => { element.inert = true; });
    const focusable = () => Array.from(navigation.querySelectorAll<HTMLElement>('a[href],button,input,select,textarea,summary,iframe,[contenteditable],[tabindex]'))
      .filter(element => element.tabIndex >= 0 && !element.matches(':disabled') && !element.closest('[inert]') && element.getClientRects().length > 0);
    const frame = requestAnimationFrame(() => { (focusable()[0] ?? navigation).focus(); });
    const keydown = (event: KeyboardEvent) => {
      // Native top-layer dialogs own focus and Escape while above navigation.
      if (document.querySelector('dialog[open]')) return;
      if (event.key === 'Escape' && !event.defaultPrevented && !navigation.querySelector('#sidebar-account-panel, [role="listbox"], [role="menu"]')) { event.preventDefault(); close.current(); }
      if (event.key !== 'Tab' || event.defaultPrevented) return;
      const targets = focusable(); const first = targets[0], last = targets[targets.length - 1];
      if (!first) { event.preventDefault(); navigation.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || !navigation.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !navigation.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', keydown);
    return () => {
      cancelAnimationFrame(frame); document.removeEventListener('keydown', keydown);
      background.forEach(({ element, inert }) => { element.inert = inert; });
      requestAnimationFrame(() => {
        // A nested popover may restore its anchor during the same Escape event.
        if (!navigation.inert || document.querySelector('dialog[open]')) return;
        const target = previous?.isConnected && !previous.closest('[inert]') && previous.getClientRects().length
          ? previous : Array.from(document.querySelectorAll<HTMLElement>(options.fallbackFocus)).find(element => !element.closest('[inert]') && element.getClientRects().length);
        target?.focus({ preventScroll: true });
      });
    };
  }, [panel, desktop, open, options]);
  return desktop;
}
