import {
  BookOpen,
  CalendarDays,
  Brain,
  ChevronDown,
  CircleHelp,
  CircleUserRound,
  LayoutGrid,
  MessageSquareText,
  Settings2,
  Sparkles,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { NavLink, Link, useLocation } from 'react-router-dom';
import mentraLogo from '../../assets/mentra-logo.png';
import { ThemeSelector } from '../theme/ThemeSelector';
import { LogoutButton } from '../auth/LogoutButton';
import { useAuth } from '../auth/AuthProvider';
import { cn } from '../../utils/cn';
import { ConversationList } from '../chat/ConversationList';

const primaryNavigation = [
  { label: 'Chat', to: '/', icon: MessageSquareText },
  { label: 'Library', to: '/library', icon: BookOpen },
  { label: 'Events', to: '/events', icon: CalendarDays },
  { label: 'Progress', to: '/progress', icon: LayoutGrid },
  { label: 'Assessments', to: '/assessments', icon: CircleHelp },
];

interface AppSidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onNewChat: () => void;
}

export function AppSidebar({
  collapsed,
  mobileOpen,
  onCloseMobile,
  onNewChat,
}: AppSidebarProps) {
  const { identity } = useAuth();
  const location = useLocation();
  const memoryActive = location.pathname === '/settings' && new URLSearchParams(location.search).get('tab') === 'memories';
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);
  const accountButtonRef = useRef<HTMLButtonElement>(null);
  const accountName = identity?.username ?? (identity?.provider ? `${identity.provider} student` : 'Learner');
  const accountMark = (identity?.username ?? identity?.provider)?.slice(0, 1).toUpperCase();

  useEffect(() => {
    if (!accountOpen) return undefined;
    function dismiss(event: PointerEvent) {
      if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false);
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setAccountOpen(false);
        accountButtonRef.current?.focus();
      }
    }
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [accountOpen]);

  return (
    <>
      {mobileOpen && (
        <button
          aria-label="Close navigation menu"
          className="fixed inset-0 z-40 bg-overlay/60 lg:hidden"
          onClick={onCloseMobile}
          type="button"
        />
      )}

      <aside
        aria-label="Main navigation"
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[17rem] flex-col border-r border-border bg-background transition-[width,transform] duration-200 ease-out lg:relative lg:z-20 lg:translate-x-0',
          collapsed && 'lg:w-[4.5rem]',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-border px-4">
          <div className="flex min-w-0 items-center gap-3">
            <img
              alt=""
              aria-hidden="true"
              className="h-8 w-8 shrink-0 object-contain"
              src={mentraLogo}
            />
            <span
              className={cn(
                'text-[15px] font-semibold tracking-tight text-foreground',
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

        <div className={cn('px-3 pt-5', collapsed && 'lg:px-2')}>
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
            <Sparkles aria-hidden="true" className="shrink-0 text-accent" size={17} />
            <span className={cn(collapsed && 'lg:hidden')}>New chat</span>
          </button>
        </div>

        <nav className={cn('space-y-1 px-3 pt-5', collapsed && 'lg:px-2')} aria-label="Workspace">
          {primaryNavigation.map(({ label, to, icon: Icon }) => (
            <NavLink
              key={to}
              aria-label={collapsed ? label : undefined}
              className={({ isActive }) =>
                cn(
                  'flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                  isActive
                    ? 'bg-active font-medium text-foreground'
                    : 'text-muted hover:bg-hover hover:text-foreground',
                  collapsed && 'lg:justify-center lg:px-0',
                )
              }
              end={to === '/'}
              onClick={() => {
                setAccountOpen(false);
                onCloseMobile();
              }}
              title={collapsed ? label : undefined}
              to={to}
            >
              <Icon aria-hidden="true" className="shrink-0" size={18} strokeWidth={1.8} />
              <span className={cn(collapsed && 'lg:hidden')}>{label}</span>
            </NavLink>
          ))}
        </nav>

        {!collapsed && (
          <ConversationList onOpen={() => { setAccountOpen(false); onCloseMobile(); }} />
        )}

        <div className={cn('mt-auto shrink-0 border-t border-border p-3', collapsed && 'lg:px-2')}>
          <div className="relative" ref={accountRef}>
            <div
              hidden={!accountOpen}
              className="absolute bottom-full left-0 z-30 mb-2 w-60 max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-xl border border-border bg-background shadow-xl shadow-black/10"
              id="sidebar-account-panel"
            >
                <div className="border-b border-border px-4 py-3">
                  <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-subtle">Signed in as</p>
                  <p className="mt-1 truncate text-sm font-medium text-foreground">{accountName}</p>
                </div>
                <div className="p-2">
                  <Link
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
                  <Link to="/settings?tab=memories" aria-current={memoryActive ? 'page' : undefined} className={cn('flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent', memoryActive ? 'bg-active font-medium text-foreground' : 'text-muted hover:bg-hover hover:text-foreground')} onClick={() => { setAccountOpen(false); onCloseMobile(); }}>
                    <Brain aria-hidden="true" className="shrink-0" size={18} strokeWidth={1.8} /><span>Memories</span>
                  </Link>
                </div>
                <div className="border-t border-border px-2 pb-2">
                  <ThemeSelector collapsed={false} />
                </div>
                <div className="border-t border-border p-2">
                  <LogoutButton />
                </div>
            </div>

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
                Account
              </span>
              <ChevronDown
                aria-hidden="true"
                className={cn('shrink-0 text-subtle transition-transform duration-150', accountOpen && 'rotate-180', collapsed && 'lg:hidden')}
                size={16}
              />
            </button>
          </div>
          {!collapsed && <p className="px-2 pb-1 pt-3 text-[11px] text-subtle">A quieter way to learn.</p>}
        </div>
      </aside>
    </>
  );
}
