import { forwardRef, useEffect, useImperativeHandle, useRef, type DialogHTMLAttributes, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { IconButton } from './IconButton';
import { cn } from '../../utils/cn';

export interface DialogProps extends DialogHTMLAttributes<HTMLDialogElement> { open?: boolean; busy?: boolean; onDismiss?: () => void; viewer?: { heading?: ReactNode; actions?: ReactNode; closeLabel?: string } }
/** Native modality keeps nested dropdowns inside the browser's top layer. */
export const Dialog = forwardRef<HTMLDialogElement, DialogProps>(function Dialog({ open, busy = false, onDismiss, className, children, onCancel, onClose, viewer, ...props }, ref) {
  const element = useRef<HTMLDialogElement>(null);
  useImperativeHandle(ref, () => element.current!, []);
  useEffect(() => {
    const dialog = element.current;
    if (!dialog || open === undefined) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
    return () => {
      const restore = dialog.contains(document.activeElement) || document.activeElement === document.body;
      if (dialog.open) dialog.close();
      if (restore) requestAnimationFrame(() => {
        if (!dialog.open && previous?.isConnected && !previous.closest('[inert]')) previous.focus();
      });
    };
  }, [open]);
  return createPortal(<dialog {...props} ref={element} aria-busy={busy || undefined} className={cn('dialog-frame', viewer && 'visual-viewer', className)} onCancel={event => {
    onCancel?.(event);
    if (busy) event.preventDefault();
    // Let native cancellation close first so the browser restores focus before
    // onClose asks the parent to remove the dialog.
  }} onClose={event => {
    // StrictMode reopens after effect cleanup before the queued close event fires.
    if (event.currentTarget.open) return;
    onClose?.(event); onDismiss?.();
  }}>{viewer ? <><header className="visual-viewer-header">
    <div className="visual-viewer-heading" dir="auto">{viewer.heading}</div>
    <div className="visual-actions">{viewer.actions}<IconButton aria-label={viewer.closeLabel ?? 'Close'} title="Close" disabled={busy} onClick={() => element.current?.close()}><X size={18} aria-hidden="true" /></IconButton></div>
  </header><div className="visual-viewer-body">{children}</div></> : children}</dialog>, document.body);
});
