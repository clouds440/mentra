import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';

/** One anchored surface for listboxes and account menus, including modal dialogs. */
export function Popover({ anchor, open, onClose, children, className, id, role, label, placement = 'below', matchWidth = false, multiselectable, focusOnOpen = false }: {
  anchor: RefObject<HTMLElement>; open: boolean; onClose: () => void; children: ReactNode;
  className?: string; id?: string; role?: string; label?: string;
  placement?: 'below' | 'above'; matchWidth?: boolean; multiselectable?: boolean; focusOnOpen?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose); close.current = onClose;
  const [style, setStyle] = useState<CSSProperties>({ visibility: 'hidden' });
  useLayoutEffect(() => {
    if (!open || !anchor.current) return;
    const position = () => {
      const trigger = anchor.current;
      if (!trigger || !trigger.isConnected || trigger.getClientRects().length === 0) { close.current(); return; }
      const rect = trigger.getBoundingClientRect(); const viewport = window.visualViewport;
      const leftEdge = (viewport?.offsetLeft ?? 0) + 12; const topEdge = (viewport?.offsetTop ?? 0) + 12;
      const rightEdge = leftEdge + (viewport?.width ?? innerWidth) - 24;
      const bottomEdge = topEdge + (viewport?.height ?? innerHeight) - 24;
      if (rect.bottom < topEdge || rect.top > bottomEdge) { close.current(); return; }
      const width = Math.min(matchWidth ? rect.width : 280, rightEdge - leftEdge);
      const above = placement === 'above' || (bottomEdge - rect.bottom < 100 && rect.top - topEdge > bottomEdge - rect.bottom);
      const available = Math.max(64, above ? rect.top - topEdge - 6 : bottomEdge - rect.bottom - 6);
      const height = Math.min(panel.current?.scrollHeight ?? 300, available, 320);
      setStyle({ position: 'fixed', width, left: Math.max(leftEdge, Math.min(rect.left, rightEdge - width)),
        top: above ? Math.max(topEdge, rect.top - height - 6) : rect.bottom + 6, maxHeight: Math.min(available, 320), visibility: 'visible' });
    };
    position();
    const focusFrame = focusOnOpen ? requestAnimationFrame(() => panel.current?.querySelector<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled)')?.focus()) : undefined;
    const observer = new ResizeObserver(position);
    observer.observe(anchor.current); if (panel.current) observer.observe(panel.current);
    const outside = (event: PointerEvent) => { if (!anchor.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) close.current(); };
    const leave = (event: FocusEvent) => { if (!anchor.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) close.current(); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); close.current(); anchor.current?.focus(); } };
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape);
    document.addEventListener('focusin', leave);
    window.addEventListener('scroll', position, true); window.addEventListener('resize', position);
    window.visualViewport?.addEventListener('resize', position); window.visualViewport?.addEventListener('scroll', position);
    return () => { if (focusFrame !== undefined) cancelAnimationFrame(focusFrame); observer.disconnect(); document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); document.removeEventListener('focusin', leave);
      window.removeEventListener('scroll', position, true); window.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('resize', position); window.visualViewport?.removeEventListener('scroll', position); };
  }, [open, anchor, placement, matchWidth, focusOnOpen]);
  if (!open) return null;
  return createPortal(<div ref={panel} id={id} role={role} aria-label={label} aria-multiselectable={multiselectable || undefined} style={style}
    className={cn('overlay-panel z-[100] overflow-y-auto rounded-xl p-1.5', className)}>{children}</div>, anchor.current?.closest('dialog[open]') ?? document.body);
}
