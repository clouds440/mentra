import { useEffect, useRef, type PointerEvent, type MouseEvent } from 'react';

/** Preserve normal taps and scrolling; consume only the click after a long press. */
export function useLongPress(onLongPress: () => void) {
  const latest = useRef(onLongPress); latest.current = onLongPress;
  const gesture = useRef<{ x: number; y: number; timer: ReturnType<typeof setTimeout> }>();
  const consumed = useRef(false);
  function cancel() { if (gesture.current) clearTimeout(gesture.current.timer); gesture.current = undefined; }
  useEffect(() => {
    window.addEventListener('scroll', cancel, true);
    return () => { cancel(); window.removeEventListener('scroll', cancel, true); };
  }, []);
  return {
    onPointerDown(event: PointerEvent) {
      cancel(); consumed.current = false;
      if (event.pointerType === 'mouse' || !event.isPrimary || event.button !== 0) return;
      gesture.current = { x: event.clientX, y: event.clientY, timer: setTimeout(() => {
        gesture.current = undefined; consumed.current = true; latest.current();
      }, 500) };
    },
    onPointerMove(event: PointerEvent) {
      const start = gesture.current;
      if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 10) cancel();
    },
    onPointerUp: cancel, onPointerCancel: cancel, onPointerLeave: cancel,
    onClickCapture(event: MouseEvent) { if (consumed.current) { consumed.current = false; event.preventDefault(); event.stopPropagation(); } },
    onContextMenu(event: MouseEvent) { event.preventDefault(); cancel(); consumed.current = true; latest.current(); },
  };
}
