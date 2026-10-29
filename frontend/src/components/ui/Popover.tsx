import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';

/** One anchored surface for listboxes and account menus, including modal dialogs. */
export function Popover({ anchor, open, onClose, children, className, id, role, label, placement = 'below', matchWidth = false, contentWidth = false, width = 280, multiselectable, focusOnOpen = false, viewportPadding = 12, maxHeight = 320 }: {
  anchor: RefObject<HTMLElement>; open: boolean; onClose: () => void; children: ReactNode;
  className?: string; id?: string; role?: string; label?: string;
  placement?: 'below' | 'above'; matchWidth?: boolean; multiselectable?: boolean; focusOnOpen?: boolean;
  viewportPadding?: number;
  maxHeight?: number;
  width?: number;
  contentWidth?: boolean;
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
      const leftEdge = (viewport?.offsetLeft ?? 0) + viewportPadding; const topEdge = (viewport?.offsetTop ?? 0) + viewportPadding;
      const rightEdge = leftEdge + (viewport?.width ?? innerWidth) - viewportPadding * 2;
      const bottomEdge = topEdge + (viewport?.height ?? innerHeight) - viewportPadding * 2;
      if (rect.bottom < topEdge || rect.top > bottomEdge) { close.current(); return; }
      const panelWidth = Math.min(contentWidth ? Math.max(rect.width, 220, Math.min(400, panel.current?.scrollWidth ?? width)) : matchWidth ? rect.width : width, rightEdge - leftEdge);
      const above = placement === 'above' || (bottomEdge - rect.bottom < 100 && rect.top - topEdge > bottomEdge - rect.bottom);
      const available = Math.max(64, above ? rect.top - topEdge - 6 : bottomEdge - rect.bottom - 6);
      const height = Math.min(panel.current?.scrollHeight ?? 300, available, maxHeight);
      const next: CSSProperties = { position: 'fixed', width: panelWidth, left: Math.max(leftEdge, Math.min(rect.left, rightEdge - panelWidth)),
        top: above ? Math.max(topEdge, rect.top - height - 6) : rect.bottom + 6, maxHeight: Math.min(available, maxHeight), visibility: 'visible' };
      setStyle(current => current.width === next.width && current.left === next.left && current.top === next.top && current.maxHeight === next.maxHeight && current.visibility === next.visibility ? current : next);
    };
    position();
    let frame: number | undefined;
    const schedulePosition = () => { if (frame === undefined) frame = requestAnimationFrame(() => { frame = undefined; position(); }); };
    const focusFrame = focusOnOpen ? requestAnimationFrame(() => panel.current?.querySelector<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled)')?.focus()) : undefined;
    const observer = new ResizeObserver(schedulePosition);
    observer.observe(anchor.current); if (panel.current) observer.observe(panel.current);
    const outside = (event: PointerEvent) => { if (!anchor.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) close.current(); };
    const leave = (event: FocusEvent) => { if (!anchor.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) close.current(); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); close.current(); anchor.current?.focus(); } };
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape);
    document.addEventListener('focusin', leave);
    window.addEventListener('scroll', schedulePosition, true); window.addEventListener('resize', schedulePosition);
    window.visualViewport?.addEventListener('resize', schedulePosition); window.visualViewport?.addEventListener('scroll', schedulePosition);
    return () => { if (frame !== undefined) cancelAnimationFrame(frame); if (focusFrame !== undefined) cancelAnimationFrame(focusFrame); observer.disconnect(); document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); document.removeEventListener('focusin', leave);
      window.removeEventListener('scroll', schedulePosition, true); window.removeEventListener('resize', schedulePosition);
      window.visualViewport?.removeEventListener('resize', schedulePosition); window.visualViewport?.removeEventListener('scroll', schedulePosition); };
  }, [open, anchor, placement, matchWidth, contentWidth, width, focusOnOpen, viewportPadding, maxHeight]);
  if (!open) return null;
  return createPortal(<div ref={panel} id={id} role={role} aria-label={label} aria-multiselectable={multiselectable || undefined} style={style}
    className={cn('overlay-panel z-[100] overflow-x-hidden overflow-y-auto overscroll-contain rounded-control p-1', className)}>{children}</div>, anchor.current?.closest('dialog[open], [data-modal-navigation]') ?? document.body);
}
