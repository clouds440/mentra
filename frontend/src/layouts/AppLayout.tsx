import { Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AppSidebar } from '../components/navigation/AppSidebar';
import { NotificationBell } from '../components/notifications/NotificationBell';

const pageTitles: Record<string, string> = {
  '/': 'New Chat',
  '/library': 'Library',
  '/progress': 'Progress',
  '/assessments': 'Assessments',
  '/settings': 'Settings',
  '/notifications': 'Notifications',
};

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [newChatKey, setNewChatKey] = useState(0);
  const isChat = location.pathname === '/' || location.pathname.startsWith('/chat/');
  const title = pageTitles[location.pathname] ?? (location.pathname.startsWith('/library/') ? 'Library' : 'Mentra');

  function startNewChat() {
    setNewChatKey((key) => key + 1);
    navigate('/');
  }

  return (
    <div className="relative flex h-dvh min-h-0 overflow-hidden bg-background text-foreground">
      <AppSidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onNewChat={startNewChat}
      />
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-start justify-between gap-3 p-3 sm:px-5" aria-label="Workspace controls">
          <div className="flex min-w-0 items-center gap-3">
            <button
              aria-label="Open navigation menu"
              className="pointer-events-auto grid h-9 w-9 place-items-center rounded-lg bg-background/90 text-muted backdrop-blur-sm hover:bg-hover hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:hidden"
              onClick={() => setMobileOpen(true)}
              type="button"
            >
              <Menu aria-hidden="true" size={19} />
            </button>
            <button
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="pointer-events-auto hidden h-9 w-9 place-items-center rounded-lg bg-background/90 text-muted backdrop-blur-sm hover:bg-hover hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:grid"
              onClick={() => setCollapsed((value) => !value)}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              type="button"
            >
              {collapsed ? (
                <PanelLeftOpen aria-hidden="true" size={18} />
              ) : (
                <PanelLeftClose aria-hidden="true" size={18} />
              )}
            </button>
            {!isChat && <span className="truncate text-sm font-medium leading-9 text-heading">{title}</span>}
          </div>
          <div className="pointer-events-auto shrink-0 rounded-lg bg-background/90 backdrop-blur-sm"><NotificationBell /></div>
        </div>
        <main className={`min-h-0 min-w-0 flex-1 overflow-hidden ${isChat ? '' : 'pt-14'}`}>
          <Outlet context={{ newChatKey }} />
        </main>
      </div>
    </div>
  );
}
