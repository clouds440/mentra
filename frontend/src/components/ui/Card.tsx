import type { HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export type CardProps = HTMLAttributes<HTMLDivElement>;

export function Card({ className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-[2rem] border border-border-strong bg-card shadow-2xl shadow-shadow/30 backdrop-blur-xl',
        className,
      )}
      {...props}
    />
  );
}
