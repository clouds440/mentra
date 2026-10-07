import {
  BookOpen,
  CircleHelp,
  LayoutGrid,
  MessageSquareText,
  Settings2,
  Sparkles,
  X,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import mentraLogo from '../../assets/mentra-logo.png';
import { ThemeSelector } from '../theme/ThemeSelector';
import { LogoutButton } from '../auth/LogoutButton';
import { cn } from '../../utils/cn';

const primaryNavigation = [
  { label: 'Chat', to: '/', icon: MessageSquareText },
  { label: 'Library', to: '/library', icon: BookOpen },
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
              onClick={onCloseMobile}
              title={collapsed ? label : undefined}
              to={to}
            >
              <Icon aria-hidden="true" className="shrink-0" size={18} strokeWidth={1.8} />
              <span className={cn(collapsed && 'lg:hidden')}>{label}</span>
            </NavLink>
          ))}
        </nav>

        {!collapsed && (
          <section aria-label="Conversation history" className="mt-8 flex-1 overflow-y-auto px-3">
            <h2 className="px-3 text-[11px] font-medium uppercase tracking-[0.12em] text-subtle">
              Recent chats
            </h2>
            <p className="px-3 py-2 text-xs leading-5 text-subtle">
              Chats are kept in memory for this session only.
            </p>
          </section>
        )}

        <div className={cn('mt-auto shrink-0 border-t border-border p-3', collapsed && 'lg:px-2')}>
          <NavLink
            aria-label={collapsed ? 'Settings' : undefined}
            className={({ isActive }) =>
              cn(
                'flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
                isActive
                  ? 'bg-active font-medium text-foreground'
                  : 'text-muted hover:bg-hover hover:text-foreground',
                collapsed && 'lg:justify-center lg:px-0',
              )
            }
            onClick={onCloseMobile}
            title={collapsed ? 'Settings' : undefined}
            to="/settings"
          >
            <Settings2 aria-hidden="true" className="shrink-0" size={18} strokeWidth={1.8} />
            <span className={cn(collapsed && 'lg:hidden')}>Settings</span>
          </NavLink>
          <ThemeSelector collapsed={collapsed} />
          <LogoutButton collapsed={collapsed} />
          {!collapsed && (
            <p className="px-3 pb-1 pt-3 text-[11px] text-subtle">A quieter way to learn.</p>
          )}
        </div>
      </aside>
    </>
  );
}
