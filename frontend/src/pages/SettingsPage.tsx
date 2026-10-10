import { Database, Sparkles } from 'lucide-react';
import { ProfileSettings } from '../components/student-profile/ProfileSettings';
import { useSearchParams } from 'react-router-dom';
import { useState, useEffect, lazy, Suspense } from 'react';
import { Spinner } from '../components/ui/Spinner';
import { NotificationSettings } from '../components/notifications/NotificationSettings';
import { AssessmentSettings } from '../components/assessments/AssessmentSettings';

const MemoriesSettings = lazy(() => import('../components/memories/MemoriesSettings').then(module => ({ default: module.MemoriesSettings })));

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
  const [params, setParams] = useSearchParams();
  const sections = ['profile', 'memories', 'notifications'] as const;
  const requested = params.get('tab');
  const tab = requested === 'memories' || requested === 'notifications' ? requested : 'profile';
  const [visitedMemories, setVisitedMemories] = useState(tab === 'memories');
  useEffect(() => { if (tab === 'memories') setVisitedMemories(true); }, [tab]);
  function changeTab(value: string) {
    if (value === 'memories') setVisitedMemories(true);
    const next = new URLSearchParams(params);
    if (value === 'profile') { next.delete('tab'); next.delete('memory'); }
    else { next.set('tab', value); if (value !== 'memories') next.delete('memory'); }
    setParams(next);
  }
  return (
    <div className="h-full overflow-y-auto">
      <div className="page-container">
        <div className="max-w-2xl">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-accent/80">
            Your workspace
          </p>
          <h1 className="mt-3 page-title">
            Settings
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted">
            Manage your profile and workspace preferences. Your conversations are saved to your Mentra account.
          </p>
        </div>

        <div role="tablist" aria-label="Settings sections" className="mt-7 flex gap-2 border-b border-border" onKeyDown={event => {
          if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
            event.preventDefault();
            const current = sections.findIndex(value => `settings-tab-${value}` === (event.target as HTMLElement).id);
            const value = event.key === 'Home' ? sections[0] : event.key === 'End' ? sections[sections.length - 1] : sections[(current + (event.key === 'ArrowRight' ? 1 : sections.length - 1)) % sections.length];
            changeTab(value); document.getElementById(`settings-tab-${value}`)?.focus();
          }
        }}>
          {sections.map(value => <button key={value} id={`settings-tab-${value}`} role="tab" aria-selected={tab === value} aria-controls={`settings-panel-${value}`} tabIndex={tab === value ? 0 : -1} className={`border-b-2 px-3 py-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${tab === value ? 'border-accent text-foreground' : 'border-transparent text-muted hover:text-foreground'}`} onClick={() => changeTab(value)}>{value === 'profile' ? 'Profile & preferences' : value === 'memories' ? 'Memories' : 'Notifications'}</button>)}
        </div>
        <div role="tabpanel" id="settings-panel-profile" aria-labelledby="settings-tab-profile" hidden={tab !== 'profile'}>
        <ProfileSettings />
        <AssessmentSettings />
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
        <div role="tabpanel" id="settings-panel-memories" aria-labelledby="settings-tab-memories" hidden={tab !== 'memories'}>
          {(visitedMemories || tab === 'memories') && <Suspense fallback={<div role="status" className="mt-7 flex items-center gap-2 text-sm text-muted"><Spinner />Loading memories…</div>}><MemoriesSettings active={tab === 'memories'} /></Suspense>}
        </div>
        <div role="tabpanel" id="settings-panel-notifications" aria-labelledby="settings-tab-notifications" hidden={tab !== 'notifications'}>
          {tab === 'notifications' && <NotificationSettings />}
        </div>
      </div>
    </div>
  );
}
