import { Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AppSidebar } from '../components/navigation/AppSidebar';
import { conversations, sampleConversations } from '../pages/chat/mockConversations';

const pageTitles: Record<string, string> = {
  '/': 'Chat',
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
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    sampleConversations[0]?.id ?? null,
  );
  const [newChatKey, setNewChatKey] = useState(0);
  const title = pageTitles[location.pathname] ?? 'Mentra';

  function startNewChat() {
    setActiveConversationId(null);
    setNewChatKey((key) => key + 1);
    navigate('/');
  }

  function selectConversation(id: string) {
    setActiveConversationId(id);
    navigate('/');
  }

  return (
    <div className="flex h-dvh min-h-[30rem] overflow-hidden bg-slate-950 text-slate-100">
      <AppSidebar
        activeConversationId={activeConversationId}
        collapsed={collapsed}
        conversations={conversations}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onNewChat={startNewChat}
        onSelectConversation={selectConversation}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[4.35rem] shrink-0 items-center justify-between border-b border-white/[0.07] px-4 sm:px-6">
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
          <span className="hidden items-center gap-2 text-xs text-slate-500 sm:flex">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Private workspace
          </span>
        </header>
        <main className="min-h-0 flex-1">
          <Outlet
            context={{ activeConversationId, newChatKey }}
          />
        </main>
      </div>
    </div>
  );
}
