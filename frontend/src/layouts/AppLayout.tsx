import { Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AppSidebar } from '../components/navigation/AppSidebar';

const pageTitles: Record<string, string> = {
  '/': 'New Chat',
  '/library': 'Library',
  '/progress': 'Progress',
  '/assessments': 'Assessments',
  '/settings': 'Settings',
};

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [newChatKey, setNewChatKey] = useState(0);
  const [chatTitle, setChatTitle] = useState('New Chat');
  const title =
    location.pathname === '/'
      ? chatTitle
      : pageTitles[location.pathname] ?? 'Mentra';

  function startNewChat() {
    setChatTitle('New Chat');
    setNewChatKey((key) => key + 1);
    navigate('/');
  }

  return (
    <div className="flex h-dvh min-h-[30rem] overflow-hidden bg-slate-950 text-slate-100">
      <AppSidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onNewChat={startNewChat}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center border-b border-white/[0.07] px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <button
              aria-label="Open navigation menu"
              className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 lg:hidden"
              onClick={() => setMobileOpen(true)}
              type="button"
            >
              <Menu aria-hidden="true" size={19} />
            </button>
            <button
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="hidden h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 lg:grid"
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
            <span className="text-sm font-medium text-slate-200">{title}</span>
          </div>
        </header>
        <main className="min-h-0 flex-1">
          <Outlet context={{ newChatKey, setChatTitle }} />
        </main>
      </div>
    </div>
  );
}
