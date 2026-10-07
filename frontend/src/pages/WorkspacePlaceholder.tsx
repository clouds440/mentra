import type { ReactNode } from 'react';

interface WorkspacePlaceholderProps {
  eyebrow: string;
  title: string;
  description: string;
  icon: ReactNode;
  emptyTitle: string;
  emptyDescription: string;
  children?: ReactNode;
}

export function WorkspacePlaceholder({
  eyebrow,
  title,
  description,
  icon,
  emptyTitle,
  emptyDescription,
  children,
}: WorkspacePlaceholderProps) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
        <div className="max-w-2xl">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-accent/80">
            {eyebrow}
          </p>
          <h1 className="mt-3 text-3xl font-medium tracking-tight text-foreground">
            {title}
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted">{description}</p>
        </div>

        {children}

        <section className="mt-10 flex min-h-64 flex-col items-center justify-center border-y border-border px-5 py-12 text-center">
          <span className="grid h-11 w-11 place-items-center rounded-xl border border-border bg-hover/50 text-muted">
            {icon}
          </span>
          <h2 className="mt-5 text-base font-medium text-heading">{emptyTitle}</h2>
          <p className="mt-2 max-w-md text-sm leading-6 text-subtle">
            {emptyDescription}
          </p>
        </section>
      </div>
    </div>
  );
}
