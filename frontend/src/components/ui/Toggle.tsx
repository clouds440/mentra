import { useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '../../utils/cn';

export interface ToggleProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'size' | 'children'> {
  checked: boolean;
  label: ReactNode;
  description?: ReactNode;
}

/** Native keyboard/form behavior with one shared, theme-aware switch design. */
export function Toggle({ label, description, className, id, checked, disabled, ...props }: ToggleProps) {
  const generatedId = useId();
  const labelId = `${id ?? generatedId}-label`;
  const descriptionId = `${id ?? generatedId}-description`;
  return (
    <label className={cn('flex items-start justify-between gap-4 text-sm', disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer', className)}>
      <span className="min-w-0 flex-1 py-2.5">
        <span id={labelId} className="font-medium text-heading">{label}</span>
        {description && <span id={descriptionId} className="mt-1 block font-normal leading-6 text-muted">{description}</span>}
      </span>
      <span className="relative flex min-h-11 w-11 shrink-0 items-center">
        <input {...props} id={id ?? generatedId} type="checkbox" role="switch" checked={checked} disabled={disabled}
          aria-labelledby={props['aria-labelledby'] ?? labelId}
          aria-describedby={[props['aria-describedby'], description ? descriptionId : undefined].filter(Boolean).join(' ') || undefined}
          className="peer absolute inset-0 z-10 m-0 h-full w-full cursor-[inherit] opacity-0" />
        <span aria-hidden="true" className="pointer-events-none relative h-6 w-11 rounded-full border border-border-strong bg-border-strong shadow-inner transition-colors duration-200 peer-checked:border-accent peer-checked:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-accent peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-background motion-reduce:transition-none">
          <span className={cn('absolute left-0.5 top-0.5 h-[18px] w-[18px] rounded-full bg-accent-foreground shadow-sm transition-transform duration-200 motion-reduce:transition-none', checked ? 'translate-x-5' : 'translate-x-0')} />
        </span>
      </span>
    </label>
  );
}
