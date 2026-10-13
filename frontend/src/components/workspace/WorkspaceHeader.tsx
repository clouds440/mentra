import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

/** Shared hierarchy for authenticated workspace pages. */
export function WorkspaceHeader({ title, description, icon: Icon, actions }: {
  title: string; description: string; icon: LucideIcon; actions?: ReactNode;
}) {
  return <header className="workspace-header">
    <div className="flex min-w-0 flex-1 basis-full items-start gap-3 sm:basis-0">
      <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-control border border-border bg-surface text-accent"><Icon size={19} strokeWidth={1.8} aria-hidden="true" /></span>
      <div className="min-w-0"><h1 className="page-title">{title}</h1><p className="mt-1.5 max-w-xl text-sm leading-6 text-muted">{description}</p></div>
    </div>
    {actions && <div className="action-row">{actions}</div>}
  </header>;
}

export function WorkspaceEmpty({ title, description, icon: Icon, action }: {
  title: string; description: string; icon: LucideIcon; action?: ReactNode;
}) {
  return <div className="workspace-empty"><span className="grid h-9 w-9 place-items-center rounded-control bg-active text-accent"><Icon size={19} aria-hidden="true" /></span><h2 className="mt-3 font-medium text-heading">{title}</h2><p className="mt-1.5 max-w-md text-sm leading-6 text-muted">{description}</p>{action && <div className="mt-4">{action}</div>}</div>;
}
