import type { HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export interface CardProps extends HTMLAttributes<HTMLDivElement> { elevated?: boolean }

export function Card({ className, elevated = false, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-panel border border-border bg-card',
        elevated && 'shadow-panel',
        className,
      )}
      {...props}
    />
  );
}
