import { useId, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '../../utils/cn';
import { Skeleton } from '../ui/Skeleton';

/** One scroll boundary and responsive content rhythm for non-chat routes. */
export function PageShell({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('workspace-page', className)}><div className="page-container">{children}</div></div>;
}
export function PageSection({ title, description, actions, children, className, ...props }: HTMLAttributes<HTMLElement> & { title?: string; description?: string; actions?: ReactNode }) {
  const id = useId();
  return <section {...props} aria-labelledby={title ? id : props['aria-labelledby']} className={cn('workspace-panel page-section', className)}>
    {(title || actions) && <header className="page-section-header"><div className="min-w-0">{title && <h2 id={id}>{title}</h2>}{description && <p>{description}</p>}</div>{actions && <div className="action-row">{actions}</div>}</header>}
    {children}
  </section>;
}
export function PageToolbar({ children, className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cn('workspace-toolbar', className)}>{children}</div>;
}
export function PageSkeleton({ layout = 'cards' }: { layout?: 'cards' | 'form' | 'table' }) {
  return <div className={cn('page-loading', layout === 'cards' && 'workspace-grid')} aria-label="Loading page content" role="status">
    {layout === 'cards' ? Array.from({ length: 4 }, (_, index) => <Skeleton key={index} variant="card" rows={1} />) : <Skeleton variant={layout} rows={4} />}
  </div>;
}
