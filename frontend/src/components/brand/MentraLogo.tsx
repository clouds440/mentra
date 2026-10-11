import type { ComponentPropsWithoutRef } from 'react';
import mentraLogo from '../../assets/mentra-logo.png';
import { cn } from '../../utils/cn';

interface MentraLogoProps extends Omit<ComponentPropsWithoutRef<'span'>, 'children'> {
  working?: boolean;
}

/** Decorative brand mark; the surrounding UI owns its accessible status/name. */
export function MentraLogo({ working = false, className, ...props }: MentraLogoProps) {
  return (
    <span {...props} aria-hidden="true" data-working={working} className={cn('mentra-logo relative inline-block h-8 w-8 shrink-0 align-middle', className)}>
      <span className="mentra-logo-mark relative block h-full w-full">
        <img alt="" draggable={false} className="block h-full w-full object-contain" src={mentraLogo} />
        {working && <span className="mentra-logo-shimmer pointer-events-none absolute inset-0" style={{ maskImage: `url(${mentraLogo})`, WebkitMaskImage: `url(${mentraLogo})` }} />}
      </span>
    </span>
  );
}
