import { forwardRef, useImperativeHandle, useRef, useState, type InputHTMLAttributes } from 'react';
import { FileUp } from 'lucide-react';
import { Button } from './Button';
import { cn } from '../../utils/cn';

export const FileInput = forwardRef<HTMLInputElement, Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { label?: string; filename?: string; variant?: 'compact' | 'dropzone'; hint?: string; onFiles?: (files: File[]) => void }>(
  function FileInput({ label = 'File', filename, className, disabled, onChange, variant = 'compact', hint, onFiles, ...props }, forwarded) {
    const input = useRef<HTMLInputElement>(null); const [selected, setSelected] = useState('');
    const [dragging, setDragging] = useState(false); const depth = useRef(0);
    useImperativeHandle(forwarded, () => input.current!, []);
    return <div className={cn('space-y-2', className)}>
      <span className="block text-sm font-medium text-heading">{label}</span>
      <div className={variant === 'dropzone' ? `file-dropzone ${dragging ? 'is-dragging' : ''} ${disabled ? 'is-disabled' : ''}` : 'flex min-w-0 items-center gap-2 rounded-control border border-border-strong bg-input p-1.5'}
        onDragEnter={event => { if (variant !== 'dropzone' || disabled || !event.dataTransfer.types.includes('Files')) return; event.preventDefault(); depth.current++; setDragging(true); }}
        onDragOver={event => { if (variant === 'dropzone' && event.dataTransfer.types.includes('Files')) { event.preventDefault(); event.dataTransfer.dropEffect = disabled ? 'none' : 'copy'; } }}
        onDragLeave={event => { if (variant !== 'dropzone') return; event.preventDefault(); if (--depth.current <= 0) { depth.current = 0; setDragging(false); } }}
        onDrop={event => {
          if (variant !== 'dropzone') return;
          event.preventDefault(); depth.current = 0; setDragging(false);
          if (disabled || !onFiles) return;
          const files = Array.from(event.dataTransfer.files); if (!files.length) return;
          if (input.current) input.current.files = event.dataTransfer.files;
          setSelected(files.map(file => file.name).join(', ')); onFiles(files);
        }}>
        <input {...props} ref={input} type="file" tabIndex={-1} aria-label={props['aria-label'] ?? label} className="sr-only" disabled={disabled}
          onInvalid={event => { event.preventDefault(); event.currentTarget.parentElement?.querySelector('button')?.focus(); }}
          onChange={event => { const files = Array.from(event.target.files ?? []); setSelected(files.map(file => file.name).join(', ')); onChange?.(event); onFiles?.(files); }} />
        {variant === 'dropzone' && <><span className="file-dropzone-icon"><FileUp size={25} strokeWidth={1.5} aria-hidden="true" /></span><p className="font-medium text-heading">{dragging ? 'Drop your file here' : 'Drop a file to get started'}</p><p className="text-sm text-muted">{hint || 'Or choose a file from your device.'}</p></>}
        <Button variant="secondary" size="sm" disabled={disabled} aria-label={`Upload ${label.toLowerCase()}`} onClick={() => input.current?.click()}><FileUp size={15} aria-hidden="true" />Browse files</Button>
        {variant === 'compact' && <span aria-live="polite" className="min-w-0 flex-1 truncate text-sm text-muted" title={filename ?? selected}>{(filename ?? selected) || 'No file selected'}</span>}
      </div>
    </div>;
  });
