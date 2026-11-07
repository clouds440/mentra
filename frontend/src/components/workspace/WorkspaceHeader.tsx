import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { m, useReducedMotion } from '../ui/Motion';

/** Shared hierarchy for authenticated workspace pages. */
export function WorkspaceHeader({ title, description, icon: Icon, actions }: {
  title: string; description: string; icon: LucideIcon; actions?: ReactNode;
}) {
  const reducedMotion = useReducedMotion();
  return <m.header className="workspace-header" initial={reducedMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: .18 }}>
    <div className="workspace-heading-group">
      <div className="workspace-eyebrow"><Icon size={14} strokeWidth={1.8} aria-hidden="true" /><span>Your learning workspace</span></div>
      <h1 className="page-title">{title}</h1>
      <p className="workspace-description">{description}</p>
    </div>
    {actions && <div className="action-row">{actions}</div>}
  </m.header>;
}

export function WorkspaceEmpty({ title, description, icon: Icon, action }: {
  title: string; description: string; icon: LucideIcon; action?: ReactNode;
}) {
  return <div className="workspace-empty"><span className="grid h-9 w-9 place-items-center rounded-control bg-active text-accent"><Icon size={19} aria-hidden="true" /></span><h2 className="mt-3 font-medium text-heading">{title}</h2><p className="mt-1.5 max-w-md text-sm leading-6 text-muted">{description}</p>{action && <div className="mt-4">{action}</div>}</div>;
}
