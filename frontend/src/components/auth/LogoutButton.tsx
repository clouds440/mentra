import { LogOut } from 'lucide-react';
import { useState } from 'react';
import { Button, Spinner } from '../ui';
import { useAuth } from './AuthProvider';
import { authErrorMessage } from '../../services/auth';
import { cn } from '../../utils/cn';

export function LogoutButton({ collapsed = false }: { collapsed?: boolean }) {
  const { logout } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function signOut() {
    if (pending) return;
    setPending(true);
    setError(null);
    try { await logout(); }
    catch (failure) { setError(authErrorMessage(failure)); }
    finally { setPending(false); }
  }
  return (
    <div>
      <Button aria-label="Sign out" title={collapsed ? 'Sign out' : undefined} variant="ghost" size="sm"
        className={cn('min-h-10 w-full justify-start gap-3 rounded-lg px-3 font-normal text-muted hover:bg-hover hover:text-foreground', collapsed && 'lg:justify-center lg:px-0')}
        disabled={pending} onClick={() => { void signOut(); }}>
        {pending ? <Spinner className="h-[18px] w-[18px] shrink-0" label="Signing out" /> : <LogOut aria-hidden="true" className="shrink-0" size={18} strokeWidth={1.8} />}
        <span className={cn(collapsed && 'lg:hidden')}>{pending ? 'Signing out…' : 'Sign out'}</span>
      </Button>
      {error && <p role="alert" className={cn('px-3 py-2 text-xs leading-5 text-danger', collapsed && 'lg:sr-only')}>{error}</p>}
    </div>
  );
}
