import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

/** Shared hierarchy for authenticated workspace pages. */
export function WorkspaceHeader({ title, description, icon: Icon, actions }: {
  title: string; description: string; icon: LucideIcon; actions?: ReactNode;
}) {
  return <header className="workspace-header">
    <div className="flex min-w-0 items-start gap-4">
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-border bg-surface text-accent"><Icon size={23} strokeWidth={1.7} aria-hidden="true" /></span>
      <div className="min-w-0"><h1 className="page-title">{title}</h1><p className="mt-2 max-w-xl text-sm leading-6 text-muted">{description}</p></div>
    </div>
    {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
  </header>;
}

export function WorkspaceEmpty({ title, description, icon: Icon, action }: {
  title: string; description: string; icon: LucideIcon; action?: ReactNode;
}) {
  return <div className="workspace-empty"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-active text-accent"><Icon size={22} aria-hidden="true" /></span><h2 className="mt-4 font-medium text-heading">{title}</h2><p className="mt-2 max-w-md text-sm leading-6 text-muted">{description}</p>{action && <div className="mt-5">{action}</div>}</div>;
}
