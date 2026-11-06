import { Dialog } from '../ui/Dialog';
import { useId, useRef, type ReactNode } from 'react';

export function MemoryConfirmation({ title, busy, error, onCancel, children }: {
  title: string; busy: boolean; error: string; onCancel: () => void; children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  return <Dialog title={title} open ref={dialog} busy={busy} onDismiss={onCancel} role="alertdialog" aria-labelledby={titleId} aria-busy={busy}
    className="max-w-lg">
    {error && <p role="alert" className="mb-3 text-sm text-danger">{error}</p>}
    {children}
  </Dialog>;
}
