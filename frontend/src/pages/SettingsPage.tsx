import { PageShell } from '../components/workspace/PageShell';
import { Tabs } from '../components/ui/Tabs';
import { Skeleton } from '../components/ui/Skeleton';
import { Database, Settings2 } from 'lucide-react';
import { WorkspaceHeader } from '../components/workspace/WorkspaceHeader';
import { ProfileSettings } from '../components/student-profile/ProfileSettings';
import { useSearchParams } from 'react-router';
import { useState, useEffect, lazy, Suspense } from 'react';
import { NotificationSettings } from '../components/notifications/NotificationSettings';
import { AssessmentSettings } from '../components/assessments/AssessmentSettings';
import { PasswordSettings } from '../components/auth/PasswordSettings';
import { ChatAppearanceSettings } from '../components/chat/ChatAppearanceSettings';
import { useAuth } from '../components/auth/AuthProvider';

const MemoriesSettings = lazy(() => import('../components/memories/MemoriesSettings').then(module => ({ default: module.MemoriesSettings })));
const ArchivedChatsSettings = lazy(() => import('../components/chat/ArchivedChatsSettings').then(module => ({ default: module.ArchivedChatsSettings })));

const settingSections = [
  {
    title: 'Your data',
    description: 'Your learner profile is linked to your Mentra account.',
    detail: 'Your conversations, learner profile, learning evidence, and progress follow your account.',
    icon: Database,
  },
];

export function SettingsPage() {
  const { identity } = useAuth();
  const canChangePassword = !!identity?.user_id && !identity.provider;
  const [params, setParams] = useSearchParams();
  const sections = ['profile', 'memories', 'notifications', 'archive'] as const;
  const requested = params.get('tab');
  const tab = requested === 'memories' || requested === 'notifications' || requested === 'archive' ? requested : 'profile';
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
    <PageShell className="settings-page">
        <WorkspaceHeader title="Settings" description="Your learning, your way. Adjust your profile, memories, and reminders." icon={Settings2} />

        <Tabs label="Settings sections" value={tab} onChange={changeTab} options={sections.map(value => ({ value, label: value === 'profile' ? 'Profile & preferences' : value === 'memories' ? 'Memories' : value === 'archive' ? 'Archived chats' : 'Notifications', id: `settings-tab-${value}`, panel: `settings-panel-${value}` }))} />
        <div role="tabpanel" id="settings-panel-profile" aria-labelledby="settings-tab-profile" hidden={tab !== 'profile'} className="settings-stack">
        <nav aria-label="Profile page sections" className="settings-jump-links"><span>On this page</span><a href="#settings-profile">Learning profile</a><a href="#settings-preferences">Preferences</a>{canChangePassword && <a href="#settings-security">Password</a>}<a href="#settings-data">Your data</a></nav>
        <div id="settings-profile"><ProfileSettings /></div>
        <div id="settings-preferences" className="settings-grid"><ChatAppearanceSettings /><AssessmentSettings /></div>
        {canChangePassword && <div id="settings-security"><PasswordSettings /></div>}
        <div id="settings-data" className="workspace-panel mt-6 divide-y divide-border">
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
        <div role="tabpanel" id="settings-panel-archive" aria-labelledby="settings-tab-archive" hidden={tab !== 'archive'}>
          {tab === 'archive' && <Suspense fallback={<Skeleton variant="list" />}><ArchivedChatsSettings /></Suspense>}
        </div>
    </PageShell>
  );
}
