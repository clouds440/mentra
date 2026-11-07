import { useId, type ComponentPropsWithoutRef, type ReactNode } from 'react';
import * as SwitchPrimitive from '@radix-ui/react-switch';
import { cn } from '../../utils/cn';

export interface ToggleProps extends Omit<ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>, 'children'> {
  checked: boolean;
  label: ReactNode;
  description?: ReactNode;
}

/** Radix owns keyboard, form participation and checked-state semantics. */
export function Toggle({ label, description, className, id, checked, disabled, ...props }: ToggleProps) {
  const generatedId = useId();
  const labelId = `${id ?? generatedId}-label`;
  const descriptionId = `${id ?? generatedId}-description`;
  return (
    <div className={cn('flex items-start justify-between gap-4 text-sm', disabled && 'opacity-60', className)}>
      <label htmlFor={id ?? generatedId} className={cn('min-w-0 flex-1 py-2', disabled ? 'cursor-not-allowed' : 'cursor-pointer')}>
        <span id={labelId} className="font-medium text-heading">{label}</span>
        {description && <span id={descriptionId} className="mt-1 block font-normal leading-6 text-muted">{description}</span>}
      </label>
      <span className="flex min-h-11 shrink-0 items-center">
        <SwitchPrimitive.Root {...props} id={id ?? generatedId} checked={checked} disabled={disabled}
          aria-labelledby={props['aria-labelledby'] ?? labelId}
          aria-describedby={[props['aria-describedby'], description ? descriptionId : undefined].filter(Boolean).join(' ') || undefined}
          className="product-switch">
          <SwitchPrimitive.Thumb className="product-switch-thumb" />
        </SwitchPrimitive.Root>
      </span>
    </div>
  );
}
