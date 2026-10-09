import { forwardRef, useImperativeHandle, useRef, useState, type InputHTMLAttributes } from 'react';
import { FileUp } from 'lucide-react';
import { Button } from './Button';
import { cn } from '../../utils/cn';

export const FileInput = forwardRef<HTMLInputElement, Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { label?: string; filename?: string }>(
  function FileInput({ label = 'File', filename, className, disabled, onChange, ...props }, forwarded) {
    const input = useRef<HTMLInputElement>(null); const [selected, setSelected] = useState('');
    useImperativeHandle(forwarded, () => input.current!, []);
    return <div className={cn('space-y-2', className)}>
      <span className="block text-sm font-medium text-heading">{label}</span>
      <div className="flex min-w-0 items-center gap-3 rounded-xl border border-border-strong bg-input p-2">
        <input {...props} ref={input} type="file" tabIndex={-1} aria-label={props['aria-label'] ?? label} className="sr-only" disabled={disabled}
          onInvalid={event => { event.preventDefault(); event.currentTarget.parentElement?.querySelector('button')?.focus(); }}
          onChange={event => { setSelected(Array.from(event.target.files ?? []).map(file => file.name).join(', ')); onChange?.(event); }} />
        <Button variant="secondary" disabled={disabled} aria-label={`Upload ${label.toLowerCase()}`} onClick={() => input.current?.click()}><FileUp size={16} aria-hidden="true" />Browse files</Button>
        <span aria-live="polite" className="min-w-0 flex-1 truncate text-sm text-muted" title={filename ?? selected}>{(filename ?? selected) || 'No file selected'}</span>
      </div>
    </div>;
  });
