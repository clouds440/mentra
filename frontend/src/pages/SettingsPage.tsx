import { Cloud, Database, Sparkles } from 'lucide-react';
import { Button } from '../components/ui';

const settingSections = [
  {
    title: 'AI',
    description: 'Model choices and learning preferences will have a home here.',
    detail: 'Provider settings are not available yet.',
    icon: Sparkles,
  },
  {
    title: 'Your data',
    description: 'Mentra is designed to keep your learner data on this device.',
    detail: 'Using Mentra does not require a Mentra account.',
    icon: Database,
  },
];

export function SettingsPage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-5 py-10 sm:px-8 sm:py-14">
        <div className="max-w-2xl">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-sky-200/80">
            Your workspace
          </p>
          <h1 className="mt-3 text-3xl font-medium tracking-tight text-slate-100">
            Settings
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Mentra works locally. Optional backup and model settings can be configured here as they become available.
          </p>
        </div>

        <div className="mt-10 divide-y divide-white/[0.07] border-y border-white/[0.07]">
          {settingSections.map(({ title, description, detail, icon: Icon }) => (
            <section className="flex gap-4 py-6 sm:gap-6" key={title}>
              <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-white/[0.08] text-slate-400">
                <Icon aria-hidden="true" size={17} strokeWidth={1.8} />
              </span>
              <div>
                <h2 className="text-sm font-medium text-slate-200">{title}</h2>
                <p className="mt-1.5 text-sm leading-6 text-slate-400">{description}</p>
                <p className="mt-2 text-xs text-slate-600">{detail}</p>
              </div>
            </section>
          ))}

          <section className="flex flex-col gap-5 py-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex gap-4 sm:gap-6">
              <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-white/[0.08] text-slate-400">
                <Cloud aria-hidden="true" size={17} strokeWidth={1.8} />
              </span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-medium text-slate-200">Optional backup</h2>
                  <span className="rounded-full border border-white/[0.08] px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-500">
                    Coming soon
                  </span>
                </div>
                <p className="mt-1.5 max-w-lg text-sm leading-6 text-slate-400">
                  Mentra can optionally back up your local data to Google Drive. Drive is for backup and restore—not for signing in.
                </p>
                <p className="mt-2 text-xs text-slate-600">
                  Mentra works locally; Google Drive is optional.
                </p>
              </div>
            </div>
            <Button className="shrink-0 self-start sm:self-auto" disabled size="sm" variant="secondary">
              Connect Google Drive
            </Button>
          </section>
        </div>
      </div>
    </div>
  );
}
