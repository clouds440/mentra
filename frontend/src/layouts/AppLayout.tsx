import { Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AppSidebar } from '../components/navigation/AppSidebar';
import { NotificationBell } from '../components/notifications/NotificationBell';
import { IconButton } from '../components/ui/IconButton';
import { useResizableSidebar } from '../hooks/useResizableSidebar';

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const sidebar = useResizableSidebar();
  const { collapsed } = sidebar;
  const [mobileOpen, setMobileOpen] = useState(false);
  const [newChatKey, setNewChatKey] = useState(0);
  const [newChatPending, setNewChatPending] = useState(false);
  const chatContext = useMemo(() => ({ newChatKey, newChatPending }), [newChatKey, newChatPending]);
  // Router transitions and local state can commit separately. Keep the old
  // composer inert until the destination and its draft reset have committed.
  useLayoutEffect(() => { setNewChatPending(false); }, [location.key]);
  const isChat = location.pathname === '/' || location.pathname.startsWith('/chat/');
  useEffect(() => {
    if (isChat) return;
    const main = document.getElementById('workspace-main');
    main?.focus({ preventScroll: true });
  }, [location.pathname]);

  function startNewChat() {
    setNewChatPending(true);
    setNewChatKey((key) => key + 1);
    navigate('/');
  }

  return (
    <div className={`relative flex h-dvh min-h-0 overflow-hidden bg-background text-foreground ${sidebar.resizing ? 'select-none' : ''}`}>
      <a href="#workspace-main" className="skip-link">Skip to content</a>
      <AppSidebar
        collapsed={collapsed}
        width={sidebar.width}
        resizing={sidebar.resizing}
        resizeHandle={<div {...sidebar.handleProps} className="group absolute inset-y-0 -right-1 z-30 hidden w-2 cursor-col-resize touch-none items-center justify-center outline-none lg:flex" title="Drag to resize · Double-click to reset"><span aria-hidden="true" className={`h-full w-0.5 rounded-full transition-colors duration-150 group-hover:bg-accent/50 group-focus-visible:bg-accent ${sidebar.resizing ? 'bg-accent/60' : ''}`} /></div>}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onNewChat={startNewChat}
      />
      <div id="workspace-content" className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <div className={`pointer-events-none absolute inset-x-0 top-0 z-30 flex items-start justify-between gap-3 p-3 sm:px-5 ${isChat ? 'chat-floating-controls' : ''}`} aria-label="Workspace controls">
          <div className="flex min-w-0 items-center gap-3">
            <IconButton
              aria-label="Open navigation menu"
              className="pointer-events-auto bg-background text-muted lg:hidden"
              onClick={() => setMobileOpen(true)}
              type="button"
            >
              <Menu aria-hidden="true" size={19} />
            </IconButton>
            <IconButton
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className="pointer-events-auto hidden bg-background text-muted lg:inline-flex"
              onClick={sidebar.toggle}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              type="button"
            >
              {collapsed ? (
                <PanelLeftOpen aria-hidden="true" size={18} />
              ) : (
                <PanelLeftClose aria-hidden="true" size={18} />
              )}
            </IconButton>
          </div>
          <div className="pointer-events-auto shrink-0 rounded-control bg-background"><NotificationBell quiet={isChat} /></div>
        </div>
        <main id="workspace-main" tabIndex={-1} className={`min-h-0 min-w-0 flex-1 overflow-hidden outline-none ${isChat ? '' : 'pt-14'}`}>
          <Outlet context={chatContext} />
        </main>
      </div>
    </div>
  );
}
