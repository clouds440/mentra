import { forwardRef } from 'react';
import { Button, type ButtonProps } from './Button';
import { cn } from '../../utils/cn';

export const IconButton = forwardRef<HTMLButtonElement, ButtonProps & { 'aria-label': string }>(function IconButton({ className, ...props }, ref) {
  // Native ref is used for overlay anchoring and focus restoration.
  return <Button {...props} ref={ref} variant={props.variant ?? 'ghost'} size="sm" className={cn('icon-control h-8 min-h-8 w-8 shrink-0 p-0', className)} />;
});
