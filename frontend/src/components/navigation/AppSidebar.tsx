import { Popover } from '../ui/Popover';
import {
  BookOpen,
  Brain,
  ChevronDown,
  CircleHelp,
  CircleUserRound,
  LayoutGrid,
  MessageSquareText,
  Settings2,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { MentraLogo } from '../brand/MentraLogo';
import { ThemeSelector } from '../theme/ThemeSelector';
import { LogoutButton } from '../auth/LogoutButton';
import { useAuth } from '../auth/AuthProvider';
import { cn } from '../../utils/cn';
import { ConversationList } from '../chat/ConversationList';
import { useMobileNavigation } from '../../hooks/useMobileNavigation';

const primaryNavigation = [
  { label: 'Chat', to: '/', icon: MessageSquareText },
  { label: 'Library', to: '/library', icon: BookOpen },
  { label: 'Progress', to: '/progress', icon: LayoutGrid },
  { label: 'Assessments', to: '/assessments', icon: CircleHelp },
];

interface AppSidebarProps {
  collapsed: boolean;
  width: number;
  resizing: boolean;
  resizeHandle: ReactNode;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onNewChat: () => void;
}

export function AppSidebar({
  collapsed,
  width,
  resizing,
  resizeHandle,
  mobileOpen,
  onCloseMobile,
  onNewChat,
}: AppSidebarProps) {
  const { identity } = useAuth();
  const location = useLocation();
  const { conversationId } = useParams();
  const owner = identity?.learner_id;
  const [lastChat, setLastChat] = useState({ owner, id: conversationId });
  useEffect(() => {
    if (conversationId || location.pathname === '/') setLastChat({ owner, id: conversationId });
  }, [conversationId, location.pathname, owner]);
  const chatTarget = conversationId ?? (lastChat.owner === owner ? lastChat.id : undefined);
  const memoryActive = location.pathname === '/settings' && new URLSearchParams(location.search).get('tab') === 'memories';
  const [accountOpen, setAccountOpen] = useState(false);
  const accountButtonRef = useRef<HTMLButtonElement>(null);
  const accountName = identity?.username ?? (identity?.provider ? `${identity.provider} student` : 'Learner');
  const accountMark = (identity?.username ?? identity?.provider)?.slice(0, 1).toUpperCase();
  const sidebar = useRef<HTMLElement>(null);
  const desktop = useMobileNavigation(sidebar, mobileOpen, onCloseMobile);
  useEffect(() => { setAccountOpen(false); }, [location.pathname, location.search, collapsed, mobileOpen]);


  return (
    <>
      {mobileOpen && !desktop && (
        <button
          aria-label="Close navigation menu"
          className="fixed inset-0 z-40 overlay-backdrop lg:hidden"
          onClick={onCloseMobile}
          type="button"
        />
      )}

      <aside
        id="main-sidebar"
        ref={sidebar}
        role={!desktop && mobileOpen ? 'dialog' : undefined}
        aria-modal={!desktop && mobileOpen ? true : undefined}
        data-modal-navigation={!desktop && mobileOpen ? true : undefined}
        tabIndex={-1}
        aria-label="Main navigation"
        style={{ '--sidebar-width': `${collapsed ? 56 : width}px` } as CSSProperties}
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[17rem] shrink-0 flex-col border-r border-border bg-background duration-200 ease-out motion-reduce:transition-none lg:relative lg:z-20 lg:w-[var(--sidebar-width)] lg:translate-x-0',
          resizing ? 'transition-none' : 'transition-[width,transform]',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
      >
        {resizeHandle}
        <div className={cn('flex h-12 shrink-0 items-center justify-between border-b border-border px-4', collapsed && 'lg:justify-center lg:px-0')}>
          <div className="flex min-w-0 items-center gap-3">
            <MentraLogo />
            <span
              className={cn(
                'text-[15px] font-semibold tracking-tight text-accent/90',
                collapsed && 'lg:hidden',
              )}
            >
              Mentra
            </span>
          </div>
          <button
            aria-label="Close navigation menu"
            className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-hover hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:hidden"
            onClick={onCloseMobile}
            type="button"
          >
            <X aria-hidden="true" size={17} />
          </button>
        </div>

        <div className={cn('px-3 pt-5', collapsed && 'lg:px-1.5')}>
          <button
            aria-label="Start a new chat"
            className={cn(
              'flex h-10 w-full items-center gap-3 rounded-lg border border-border px-3 text-sm font-medium text-heading transition-colors hover:border-border-strong hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
              collapsed && 'lg:justify-center lg:px-0',
            )}
            onClick={() => {
              setAccountOpen(false);
              onNewChat();
              onCloseMobile();
            }}
            title={collapsed ? 'New chat' : undefined}
            type="button"
          >
            <svg aria-hidden="true" className="h-[18px] w-[18px] shrink-0 text-heading" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3H5a2 2 0 0 0-2 2v15l4-4h12a2 2 0 0 0 2-2v-3" />
              <path d="m15 7 5-5 3 3-5 5-4 1 1-4Z" />
              <path d="m18 4 3 3" />
            </svg>
            <span className={cn(collapsed && 'lg:hidden')}>New chat</span>
          </button>
        </div>

        <nav className={cn('space-y-1 px-3 pt-5', collapsed && 'lg:px-1.5')} aria-label="Workspace">
          {primaryNavigation.map(({ label, to, icon: Icon }) => {
            const isActive = to === '/' ? location.pathname === '/' : location.pathname === to || location.pathname.startsWith(`${to}/`);
            return (
            <Link
              key={to}
              onPointerEnter={() => { if (!isActive) void import('../../services/pagePrefetch').then(module => module.prefetchPage(to)); }}
              onFocus={() => { if (!isActive) void import('../../services/pagePrefetch').then(module => module.prefetchPage(to)); }}
              aria-label={collapsed ? label : undefined}
              aria-current={isActive ? 'page' : undefined}
              className={
                cn(
                  'flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                  isActive
                    ? 'bg-active font-medium text-foreground'
                    : 'text-muted hover:bg-hover hover:text-foreground',
                  collapsed && 'lg:justify-center lg:px-0',
                )
              }
              onClick={() => {
                setAccountOpen(false);
                onCloseMobile();
              }}
              title={collapsed ? label : undefined}
              to={to === '/' && chatTarget ? `/chat/${chatTarget}` : to}
            >
              <Icon aria-hidden="true" className="shrink-0" size={18} strokeWidth={1.8} />
              <span className={cn(collapsed && 'lg:hidden')}>{label}</span>
            </Link>
          );
          })}
        </nav>

        {(!collapsed || !desktop) && (
          <ConversationList onOpen={() => { setAccountOpen(false); onCloseMobile(); }} />
        )}

        <div className={cn('mt-auto shrink-0 border-t border-border p-3', collapsed && 'lg:px-1.5')}>
          <div className="relative">
            <Popover anchor={accountButtonRef} open={accountOpen} onClose={() => setAccountOpen(false)} placement="above" width={240} matchWidth={!collapsed || mobileOpen} viewportPadding={8} maxHeight={480} id="sidebar-account-panel" label="Account settings" className="p-0" focusOnOpen>
                <div className="border-b border-border px-4 py-3">
                  <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-subtle">Signed in as</p>
                  <p className="mt-1 truncate text-sm font-medium text-foreground">{accountName}</p>
                </div>
                <div className="p-2">
                  <Link
                    aria-label="Settings"
                    aria-current={location.pathname === '/settings' && !memoryActive ? 'page' : undefined}
                    className={
                      cn(
                        'flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                        location.pathname === '/settings' && !memoryActive
                          ? 'bg-active font-medium text-foreground'
                          : 'text-muted hover:bg-hover hover:text-foreground',
                      )
                    }
                    onClick={() => {
                      setAccountOpen(false);
                      onCloseMobile();
                    }}
                    to="/settings"
                  >
                    <Settings2 aria-hidden="true" className="shrink-0" size={18} strokeWidth={1.8} />
                    <span>Settings</span>
                  </Link>
                  <Link to="/settings?tab=memories" aria-label="Memories" aria-current={memoryActive ? 'page' : undefined} className={cn('flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent', memoryActive ? 'bg-active font-medium text-foreground' : 'text-muted hover:bg-hover hover:text-foreground')} onClick={() => { setAccountOpen(false); onCloseMobile(); }}>
                    <Brain aria-hidden="true" className="shrink-0" size={18} strokeWidth={1.8} /><span>Memories</span>
                  </Link>
                </div>
                <div className="border-t border-border px-2 pb-2">
                  <ThemeSelector collapsed={false} vertical />
                </div>
                <div className="border-t border-border p-2">
                  <LogoutButton />
                </div>
            </Popover>

            <button
              aria-controls="sidebar-account-panel"
              aria-expanded={accountOpen}
              aria-label={`Account menu for ${accountName}`}
              className={cn(
                'flex min-h-11 w-full items-center gap-3 rounded-lg px-2 text-left text-sm transition-colors hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                collapsed && 'lg:justify-center lg:px-0',
                accountOpen && 'bg-hover',
              )}
              onClick={() => setAccountOpen((open) => !open)}
              ref={accountButtonRef}
              title={collapsed ? 'Account' : undefined}
              type="button"
            >
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-active text-xs font-semibold text-foreground">
                {accountMark ?? <CircleUserRound aria-hidden="true" size={16} />}
              </span>
              <span className={cn('min-w-0 flex-1 truncate font-medium text-foreground', collapsed && 'lg:hidden')}>
                {accountName}
              </span>
              <ChevronDown
                aria-hidden="true"
                className={cn('shrink-0 text-subtle transition-transform duration-150', accountOpen && 'rotate-180', collapsed && 'lg:hidden')}
                size={16}
              />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
