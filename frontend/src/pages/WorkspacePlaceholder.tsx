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
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-sky-200/80">
            {eyebrow}
          </p>
          <h1 className="mt-3 text-3xl font-medium tracking-tight text-slate-100">
            {title}
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">{description}</p>
        </div>

        {children}

        <section className="mt-10 flex min-h-64 flex-col items-center justify-center border-y border-white/[0.07] px-5 py-12 text-center">
          <span className="grid h-11 w-11 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.025] text-slate-400">
            {icon}
          </span>
          <h2 className="mt-5 text-base font-medium text-slate-200">{emptyTitle}</h2>
          <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
            {emptyDescription}
          </p>
        </section>
      </div>
    </div>
  );
}
