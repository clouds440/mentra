import { Cloud, Database, Sparkles } from 'lucide-react';
import { Button } from '../components/ui';
import { ProfileSettings } from '../components/student-profile/ProfileSettings';

const settingSections = [
  {
    title: 'AI',
    description: 'Your learning preferences are saved in your profile above.',
    detail: 'Provider settings are not available yet.',
    icon: Sparkles,
  },
  {
    title: 'Your data',
    description: 'Your learner profile is linked to your Mentra account.',
    detail: 'Your learning evidence and progress follow your account.',
    icon: Database,
  },
];

export function SettingsPage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-5 py-10 sm:px-8 sm:py-14">
        <div className="max-w-2xl">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-accent/80">
            Your workspace
          </p>
          <h1 className="mt-3 text-3xl font-medium tracking-tight text-foreground">
            Settings
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted">
            Your workspace preferences live here. Optional backup and model settings will be available as Mentra grows.
          </p>
        </div>

        <ProfileSettings />
        <div className="mt-6 divide-y divide-border border-y border-border">
          {settingSections.map(({ title, description, detail, icon: Icon }) => (
            <section className="flex gap-4 py-6 sm:gap-6" key={title}>
              <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-border text-muted">
                <Icon aria-hidden="true" size={17} strokeWidth={1.8} />
              </span>
              <div>
                <h2 className="text-sm font-medium text-heading">{title}</h2>
                <p className="mt-1.5 text-sm leading-6 text-muted">{description}</p>
                <p className="mt-2 text-xs text-subtle">{detail}</p>
              </div>
            </section>
          ))}

          <section className="flex flex-col gap-5 py-6 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex gap-4 sm:gap-6">
              <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-border text-muted">
                <Cloud aria-hidden="true" size={17} strokeWidth={1.8} />
              </span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-medium text-heading">Optional backup</h2>
                  <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wider text-subtle">
                    Coming soon
                  </span>
                </div>
                <p className="mt-1.5 max-w-lg text-sm leading-6 text-muted">
                  Mentra can optionally back up your local data to Google Drive. Drive is for backup and restore—not for signing in.
                </p>
                <p className="mt-2 text-xs text-subtle">
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
