import { forwardRef, useEffect, useId, useImperativeHandle, useRef, type DialogHTMLAttributes, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';
import { X } from 'lucide-react';
import { IconButton } from './IconButton';

export interface DialogProps extends Omit<DialogHTMLAttributes<HTMLDialogElement>, 'title'> { title: ReactNode; open?: boolean; busy?: boolean; onDismiss?: () => void; closeLabel?: string; headerActions?: ReactNode; layout?: 'default' | 'viewer'; dismissOnBackdrop?: boolean }
/** Native modality keeps nested dropdowns inside the browser's top layer. */
export const Dialog = forwardRef<HTMLDialogElement, DialogProps>(function Dialog({ title, open, busy = false, onDismiss, className, children, onCancel, onClose, onClick, closeLabel = 'Close', headerActions, layout = 'default', dismissOnBackdrop = false, ...props }, ref) {
  const element = useRef<HTMLDialogElement>(null);
  const generatedTitleId = useId();
  const titleId = props['aria-labelledby'] || generatedTitleId;
  useImperativeHandle(ref, () => element.current!, []);
  useEffect(() => {
    const dialog = element.current;
    if (!dialog || open === undefined) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (open && !dialog.open) {
      dialog.showModal();
      // Preserve a form/confirmation's original initial focus now that shared
      // chrome precedes its content. Viewer toolbars retain native focus order.
      const initial = dialog.querySelector<HTMLElement>('.dialog-content [autofocus]')
        ?? (layout === 'default' ? dialog.querySelector<HTMLElement>('.dialog-content button:not(:disabled), .dialog-content input:not(:disabled):not([type="hidden"]), .dialog-content select:not(:disabled), .dialog-content textarea:not(:disabled), .dialog-content a[href]') : null);
      initial?.focus({ preventScroll: true });
    }
    if (!open && dialog.open) dialog.close();
    return () => {
      const restore = dialog.contains(document.activeElement) || document.activeElement === document.body;
      if (dialog.open) dialog.close();
      if (restore) requestAnimationFrame(() => {
        if (!dialog.open && previous?.isConnected && !previous.closest('[inert]')) previous.focus();
      });
    };
  }, [open, layout]);
  return createPortal(<dialog {...props} aria-labelledby={props['aria-labelledby'] || (props['aria-label'] ? undefined : titleId)} ref={element} data-layout={layout} aria-busy={busy || undefined} className={cn('dialog-frame', className)} onClick={event => {
    onClick?.(event);
    if (!dismissOnBackdrop || busy || event.defaultPrevented || event.target !== event.currentTarget) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.currentTarget.close();
  }} onCancel={event => {
    onCancel?.(event);
    if (busy) event.preventDefault();
    // Let native cancellation close first so the browser restores focus before
    // onClose asks the parent to remove the dialog.
  }} onClose={event => {
    // StrictMode reopens after effect cleanup before the queued close event fires.
    if (event.currentTarget.open) return;
    onClose?.(event); onDismiss?.();
  }}><header className="dialog-chrome"><h2 id={titleId} className="dialog-heading" dir="auto">{title}</h2>{headerActions}<IconButton aria-label={closeLabel} title="Close" disabled={busy} onClick={() => element.current?.close()}><X size={18} aria-hidden="true" /></IconButton></header><div className="dialog-content">{children}</div></dialog>, document.body);
});
