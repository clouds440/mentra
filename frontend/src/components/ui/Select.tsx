import type { SelectHTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn('min-h-11 w-full rounded-xl border border-border-strong bg-input px-3 py-2.5 text-foreground outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50', className)} {...props} />;
}
