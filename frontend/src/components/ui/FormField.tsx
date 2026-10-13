import { useId, type ReactNode } from 'react';

export function FormField({ label, id, hint, error, children }: { label: string; id?: string; hint?: ReactNode; error?: string; children: (props: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: true }) => ReactNode }) {
  const generated = useId(); const controlId = id ?? generated;
  const descriptionId = `${controlId}-description`;
  return <div className="space-y-1.5"><label htmlFor={controlId} className="block text-sm font-medium text-heading">{label}</label>{children({ id: controlId, 'aria-describedby': error || hint ? descriptionId : undefined, 'aria-invalid': error ? true : undefined })}{(error || hint) && <p id={descriptionId} role={error ? 'alert' : undefined} className={`text-xs leading-5 ${error ? 'text-danger' : 'text-muted'}`}>{error || hint}</p>}</div>;
}
