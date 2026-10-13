import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '../../utils/cn';
import { Spinner } from './Spinner';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
}

const variantClasses: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary: 'border border-transparent bg-primary text-accent-foreground hover:bg-primary-hover',
  secondary: 'border border-border-strong bg-card text-heading hover:bg-hover hover:border-border-hover',
  ghost: 'text-heading hover:bg-active',
  danger: 'border border-danger/25 bg-danger/10 text-danger hover:bg-danger/15',
};

const sizeClasses: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'min-h-8 px-2.5 text-xs',
  md: 'min-h-9 px-3 text-sm',
  lg: 'min-h-10 px-4 text-sm',
};

export function buttonStyles({ variant = 'primary', size = 'md', className }: Pick<ButtonProps, 'variant' | 'size' | 'className'> = {}) {
  return cn('ui-button relative inline-flex shrink-0 items-center justify-center gap-1.5 rounded-control font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50', variantClasses[variant], sizeClasses[size], className);
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({
  className,
  variant = 'primary',
  size = 'md',
  type = 'button',
  loading = false,
  children,
  ...props
}: ButtonProps, ref) {
  return (
    <button
      className={buttonStyles({ variant, size, className })}
      type={type}
      ref={ref}
      {...props}
      disabled={props.disabled || loading}
      aria-busy={loading || undefined}
    >{loading && <Spinner aria-hidden="true" className="absolute h-4 w-4" />}<span className={cn('inline-flex items-center justify-center gap-1.5', loading && 'opacity-0')}>{children}</span></button>
  );
});
