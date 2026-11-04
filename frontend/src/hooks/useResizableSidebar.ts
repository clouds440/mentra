import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

const navigation = { min: 220, max: 400, initial: 272, rail: 56, storageKey: 'mentra.sidebar.layout.v1',
  side: 'left', id: 'main-sidebar', label: 'Resize sidebar', desktopQuery: '(min-width: 1024px)' };
interface Layout { width: number; collapsed: boolean }

function savedLayout({ min, max, initial, rail, storageKey }: typeof navigation): Layout {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
    if (saved && typeof saved.width === 'number' && Number.isFinite(saved.width)) {
      return { width: Math.min(max, Math.max(min, saved.width)), collapsed: !!rail && saved.collapsed === true };
    }
  } catch { /* Storage can be unavailable; resizing remains usable. */ }
  return { width: initial, collapsed: false };
}

/** Pointer capture keeps resizing local to the handle, including fast drags. */
export function useResizableSidebar(options = navigation) {
  const { min, max, initial, rail, storageKey, side, id, label, desktopQuery } = options;
  const direction = side === 'left' ? 1 : -1;
  const [layout, setLayout] = useState(() => savedLayout(options));
  const [resizing, setResizing] = useState(false);
  const drag = useRef<{ pointer: number; x: number; width: number; original: Layout; handle: HTMLElement }>();
  useEffect(() => {
    if (!resizing) try { localStorage.setItem(storageKey, JSON.stringify(layout)); } catch { /* Optional preference. */ }
  }, [layout, resizing, storageKey]);

  function finish(cancel = false) {
    const active = drag.current;
    if (!active) return;
    drag.current = undefined;
    if (cancel) setLayout(active.original);
    if (active.handle.hasPointerCapture(active.pointer)) active.handle.releasePointerCapture(active.pointer);
    setResizing(false);
  }
  useEffect(() => {
    const desktop = matchMedia(desktopQuery);
    const changed = () => { if (!desktop.matches) finish(true); };
    desktop.addEventListener('change', changed);
    return () => {
      desktop.removeEventListener('change', changed);
      const active = drag.current;
      if (active?.handle.hasPointerCapture(active.pointer)) active.handle.releasePointerCapture(active.pointer);
    };
  }, [desktopQuery]);

  function move(event: PointerEvent<HTMLElement>) {
    const active = drag.current;
    if (!active || active.pointer !== event.pointerId) return;
    const width = active.width + direction * (event.clientX - active.x);
    setLayout(rail && width < min ? { width: active.original.width, collapsed: true }
      : { width: Math.max(min, Math.min(max, Math.round(width))), collapsed: false });
  }
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape' && drag.current) { event.preventDefault(); finish(true); return; }
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) && !(rail && event.key === 'Enter')) return;
    event.preventDefault();
    setLayout(previous => {
      if (event.key === 'Home') return rail ? { ...previous, collapsed: true } : { width: min, collapsed: false };
      if (event.key === 'End') return { width: max, collapsed: false };
      if (event.key === 'Enter') return { ...previous, collapsed: !previous.collapsed };
      if (previous.collapsed) return event.key === 'ArrowRight' ? { ...previous, collapsed: false } : previous;
      const width = previous.width + direction * (event.key === 'ArrowRight' ? 16 : -16);
      return rail && width < min ? { ...previous, collapsed: true } : { width: Math.max(min, Math.min(max, width)), collapsed: false };
    });
  }
  return {
    ...layout, resizing,
    toggle: () => setLayout(previous => ({ ...previous, collapsed: !previous.collapsed })),
    handleProps: {
      role: 'separator', tabIndex: 0, 'aria-label': label,
      'aria-orientation': 'vertical' as const, 'aria-valuemin': rail || min, 'aria-valuemax': max,
      'aria-valuenow': layout.collapsed ? rail : layout.width,
      'aria-valuetext': layout.collapsed ? 'Collapsed' : `${layout.width} pixels`,
      'aria-controls': id,
      onPointerDown(event: PointerEvent<HTMLElement>) {
        if (event.button !== 0 || !event.isPrimary || drag.current) return;
        event.preventDefault();
        event.currentTarget.focus({ preventScroll: true });
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { pointer: event.pointerId, x: event.clientX,
          width: event.currentTarget.parentElement?.getBoundingClientRect().width ?? layout.width,
          original: layout, handle: event.currentTarget };
        setResizing(true);
      },
      onPointerMove: move,
      onPointerUp(event: PointerEvent<HTMLElement>) { move(event); finish(); },
      onPointerCancel: () => finish(true),
      onLostPointerCapture: () => finish(),
      onKeyDown,
      onDoubleClick: () => setLayout({ width: initial, collapsed: false }),
    },
  };
}
