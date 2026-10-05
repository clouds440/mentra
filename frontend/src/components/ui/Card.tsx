import type { HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export type CardProps = HTMLAttributes<HTMLDivElement>;

export function Card({ className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-[2rem] border border-white/10 bg-slate-900/60 shadow-2xl shadow-black/30 backdrop-blur-xl',
        className,
      )}
      {...props}
    />
  );
}
