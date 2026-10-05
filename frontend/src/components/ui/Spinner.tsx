import type { SVGProps } from 'react';
import { cn } from '../../utils/cn';

export interface SpinnerProps extends SVGProps<SVGSVGElement> {
  label?: string;
}

export function Spinner({ className, label = 'Loading', ...props }: SpinnerProps) {
  return (
    <svg
      aria-label={label}
      className={cn('h-5 w-5 animate-spin text-current', className)}
      fill="none"
      role="status"
      viewBox="0 0 24 24"
      {...props}
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="3"
      />
      <path
        className="opacity-90"
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="3"
      />
    </svg>
  );
}
