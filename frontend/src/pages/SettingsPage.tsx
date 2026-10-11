import { Skeleton } from '../components/ui/Skeleton';
import { Database, Settings2 } from 'lucide-react';
import { WorkspaceHeader } from '../components/workspace/WorkspaceHeader';
import { ProfileSettings } from '../components/student-profile/ProfileSettings';
import { useSearchParams } from 'react-router-dom';
import { useState, useEffect, lazy, Suspense } from 'react';
import { NotificationSettings } from '../components/notifications/NotificationSettings';
import { AssessmentSettings } from '../components/assessments/AssessmentSettings';

const MemoriesSettings = lazy(() => import('../components/memories/MemoriesSettings').then(module => ({ default: module.MemoriesSettings })));

const settingSections = [
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
        <WorkspaceHeader title="Settings" description="Make Mentra feel right for you. Manage your learning profile, saved memories and reminders." icon={Settings2} />

        <div role="tablist" aria-label="Settings sections" className="workspace-tabs" onKeyDown={event => {
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
        <div className="workspace-panel mt-6 divide-y divide-border">
          {settingSections.map(({ title, description, detail, icon: Icon }) => (
            <section className="flex gap-4 sm:gap-6" key={title}>
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
          {(visitedMemories || tab === 'memories') && <Suspense fallback={<Skeleton variant="form" />}><MemoriesSettings active={tab === 'memories'} /></Suspense>}
        </div>
        <div role="tabpanel" id="settings-panel-notifications" aria-labelledby="settings-tab-notifications" hidden={tab !== 'notifications'}>
          {tab === 'notifications' && <NotificationSettings />}
        </div>
      </div>
    </div>
  );
}
