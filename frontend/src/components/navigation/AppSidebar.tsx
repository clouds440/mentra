import { Popover } from '../ui/Popover';
import {
  BookOpen,
  Brain,
  ChevronDown,
  CircleUserRound,
  ClipboardCheck,
  LayoutGrid,
  MessageSquareText,
  Settings2,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Link, useLocation, useParams } from 'react-router';
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
  { label: 'Assessments', to: '/assessments', icon: ClipboardCheck },
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
  const accountName = identity?.username ?? 'Learner';
  const accountMark = identity?.username ? Array.from(identity.username)[0]?.toLocaleUpperCase() : undefined;
  const accountAvatar = <span className="sidebar-account-avatar" aria-hidden="true">{accountMark ?? <CircleUserRound size={16} />}</span>;
  const sidebar = useRef<HTMLElement>(null);
  const desktop = useMobileNavigation(sidebar, mobileOpen, onCloseMobile);
  function closeAccountNavigation() {
    setAccountOpen(false);
    onCloseMobile();
  }
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
          'product-sidebar fixed inset-y-0 left-0 z-50 flex w-[17rem] shrink-0 flex-col border-r border-border bg-surface duration-200 ease-out motion-reduce:transition-none lg:relative lg:z-20 lg:w-[var(--sidebar-width)] lg:translate-x-0',
          resizing ? 'transition-none' : 'transition-[width,transform]',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
      >
        {resizeHandle}
        <div className={cn('sidebar-brand flex h-16 shrink-0 items-center justify-between px-5', collapsed && 'lg:justify-center lg:px-0')}>
          <div className="flex min-w-0 items-center gap-3">
            <MentraLogo />
            <span
              className={cn(
                'text-xl font-semibold tracking-tight text-heading',
                collapsed && 'lg:hidden',
              )}
            >
              mentra
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

        <div className={cn('px-3 pt-4', collapsed && 'lg:px-1.5')}>
          <button
            aria-label="Start a new chat"
            className={cn(
              'sidebar-new-chat flex h-10 w-full items-center gap-3 rounded-control border border-border bg-card px-3 text-sm font-medium text-heading transition-colors hover:border-border-strong hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
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

        <nav className={cn('space-y-1 px-3 pt-4', collapsed && 'lg:px-1.5')} aria-label="Workspace">
          <p className={cn('sidebar-section-label', collapsed && 'lg:hidden')}>Workspace</p>
          {primaryNavigation.map(({ label, to, icon: Icon }) => {
            const isActive = to === '/' ? location.pathname === '/' || location.pathname.startsWith('/chat/') : location.pathname === to || location.pathname.startsWith(`${to}/`);
            return (
            <Link
              key={to}
              onPointerEnter={() => { if (!isActive) void import('../../services/pagePrefetch').then(module => module.prefetchPage(to)); }}
              onFocus={() => { if (!isActive) void import('../../services/pagePrefetch').then(module => module.prefetchPage(to)); }}
              aria-label={collapsed ? label : undefined}
              aria-current={isActive ? 'page' : undefined}
              className={
                cn(
                  'sidebar-nav-link flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                  isActive
                    ? 'bg-active font-medium text-accent'
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
          <ConversationList onOpen={() => { setAccountOpen(false); onCloseMobile(); }} onNewChat={onNewChat} />
        )}

        <div className={cn('mt-auto shrink-0 p-3 pt-4', collapsed && 'lg:px-1.5')}>
          <div className="relative">
            <Popover anchor={accountButtonRef} open={accountOpen} onClose={() => setAccountOpen(false)} placement="above" width={240} matchWidth={!collapsed || mobileOpen} viewportPadding={8} maxHeight={480} id="sidebar-account-panel" label="Account settings" className="sidebar-account-drawer" focusOnOpen>
              <div className="sidebar-account-heading">{accountAvatar}<span className="truncate">{accountName}</span></div>
              <nav aria-label="Account">
                <Link to="/settings" aria-current={location.pathname === '/settings' && !memoryActive ? 'page' : undefined}
                  className="sidebar-account-link" onClick={closeAccountNavigation}>
                  <Settings2 aria-hidden="true" size={16} strokeWidth={1.8} /><span>Settings</span>
                </Link>
                <Link to="/settings?tab=memories" aria-current={memoryActive ? 'page' : undefined}
                  className="sidebar-account-link" onClick={closeAccountNavigation}>
                  <Brain aria-hidden="true" size={16} strokeWidth={1.8} /><span>Memories</span>
                </Link>
              </nav>
              <ThemeSelector collapsed={false} />
              <div className="sidebar-account-signout"><LogoutButton /></div>
            </Popover>

            <button
              aria-controls="sidebar-account-panel"
              aria-expanded={accountOpen}
              aria-label={`Account menu for ${accountName}`}
              className={cn(
                'sidebar-account-trigger',
                collapsed && 'lg:justify-center lg:px-0',
              )}
              onClick={() => setAccountOpen((open) => !open)}
              ref={accountButtonRef}
              title={collapsed ? 'Account' : undefined}
              type="button"
            >
              {accountAvatar}
              <span className={cn('min-w-0 flex-1 truncate font-medium', collapsed && 'lg:hidden')}>{accountName}</span>
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
