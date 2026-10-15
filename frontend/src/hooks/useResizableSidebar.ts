import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

const MIN = 220, MAX = 400, DEFAULT = 272, COLLAPSED = 56;
const STORAGE_KEY = 'mentra.sidebar.layout.v1';
interface Layout { width: number; collapsed: boolean }

function savedLayout(): Layout {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');
    if (saved && typeof saved.width === 'number' && Number.isFinite(saved.width)) {
      return { width: Math.min(MAX, Math.max(MIN, saved.width)), collapsed: saved.collapsed === true };
    }
  } catch { /* Storage can be unavailable; resizing remains usable. */ }
  return { width: DEFAULT, collapsed: false };
}

/** Pointer capture keeps resizing local to the handle, including fast drags. */
export function useResizableSidebar() {
  const [layout, setLayout] = useState(savedLayout);
  const [resizing, setResizing] = useState(false);
  const drag = useRef<{ pointer: number; x: number; width: number; original: Layout; handle: HTMLElement }>();
  useEffect(() => {
    if (!resizing) try { localStorage.setItem(STORAGE_KEY, JSON.stringify(layout)); } catch { /* Optional preference. */ }
  }, [layout, resizing]);

  function finish(cancel = false) {
    const active = drag.current;
    if (!active) return;
    drag.current = undefined;
    if (cancel) setLayout(active.original);
    if (active.handle.hasPointerCapture(active.pointer)) active.handle.releasePointerCapture(active.pointer);
    setResizing(false);
  }
  useEffect(() => {
    const desktop = matchMedia('(min-width: 1024px)');
    const changed = () => { if (!desktop.matches) finish(true); };
    desktop.addEventListener('change', changed);
    return () => {
      desktop.removeEventListener('change', changed);
      const active = drag.current;
      if (active?.handle.hasPointerCapture(active.pointer)) active.handle.releasePointerCapture(active.pointer);
    };
  }, []);

  function move(event: PointerEvent<HTMLElement>) {
    const active = drag.current;
    if (!active || active.pointer !== event.pointerId) return;
    const width = active.width + event.clientX - active.x;
    setLayout(width < MIN ? { width: active.original.width, collapsed: true }
      : { width: Math.min(MAX, Math.round(width)), collapsed: false });
  }
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape' && drag.current) { event.preventDefault(); finish(true); return; }
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter'].includes(event.key)) return;
    event.preventDefault();
    setLayout(previous => {
      if (event.key === 'Home') return { ...previous, collapsed: true };
      if (event.key === 'End') return { width: MAX, collapsed: false };
      if (event.key === 'Enter') return { ...previous, collapsed: !previous.collapsed };
      if (previous.collapsed) return event.key === 'ArrowRight' ? { ...previous, collapsed: false } : previous;
      const width = previous.width + (event.key === 'ArrowRight' ? 16 : -16);
      return width < MIN ? { ...previous, collapsed: true } : { width: Math.min(MAX, width), collapsed: false };
    });
  }
  return {
    ...layout, resizing,
    toggle: () => setLayout(previous => ({ ...previous, collapsed: !previous.collapsed })),
    handleProps: {
      role: 'separator', tabIndex: 0, 'aria-label': 'Resize sidebar',
      'aria-orientation': 'vertical' as const, 'aria-valuemin': COLLAPSED, 'aria-valuemax': MAX,
      'aria-valuenow': layout.collapsed ? COLLAPSED : layout.width,
      'aria-valuetext': layout.collapsed ? 'Collapsed' : `${layout.width} pixels`,
      'aria-controls': 'main-sidebar',
      onPointerDown(event: PointerEvent<HTMLElement>) {
        if (event.button !== 0 || !event.isPrimary || drag.current) return;
        event.preventDefault();
        event.currentTarget.focus({ preventScroll: true });
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { pointer: event.pointerId, x: event.clientX,
          width: layout.collapsed ? COLLAPSED : layout.width, original: layout, handle: event.currentTarget };
        setResizing(true);
      },
      onPointerMove: move,
      onPointerUp(event: PointerEvent<HTMLElement>) { move(event); finish(); },
      onPointerCancel: () => finish(true),
      onLostPointerCapture: () => finish(),
      onKeyDown,
      onDoubleClick: () => setLayout({ width: DEFAULT, collapsed: false }),
    },
  };
}
