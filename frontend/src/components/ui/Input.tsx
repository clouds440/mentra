import type { InputHTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'min-h-11 w-full rounded-xl border border-border-strong bg-input px-3 text-foreground outline-none placeholder:text-subtle focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  );
}
