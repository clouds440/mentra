import { Database, Sparkles } from 'lucide-react';
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
    detail: 'Your conversations, learner profile, learning evidence, and progress follow your account.',
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
            Manage your profile and workspace preferences. Your conversations are saved to your Mentra account.
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


        </div>
      </div>
    </div>
  );
}
