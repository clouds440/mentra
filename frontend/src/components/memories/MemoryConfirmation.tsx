import { useEffect, useId, useRef, type ReactNode } from 'react';

export function MemoryConfirmation({ title, busy, error, onCancel, children }: {
  title: string; busy: boolean; error: string; onCancel: () => void; children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return <dialog ref={dialog} role="alertdialog" aria-labelledby={titleId} aria-busy={busy}
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}
    className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-2xl border border-border bg-popover p-5 text-foreground shadow-xl">
    <h3 id={titleId} className="mb-3 font-medium text-heading">{title}</h3>
    {error && <p role="alert" className="mb-3 text-sm text-danger">{error}</p>}
    {children}
  </dialog>;
}
