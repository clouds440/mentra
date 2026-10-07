import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { Button, Spinner } from '../ui';
import { useAuth } from './AuthProvider';
import { StudentProfileProvider } from '../student-profile/StudentProfileProvider';

const appPaths = new Set(['/', '/library', '/progress', '/assessments', '/settings']);

export function returnPath(state: unknown): string {
  if (typeof state !== 'object' || state === null || !('from' in state) || typeof state.from !== 'string') return '/';
  const path = state.from;
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return '/';
  return appPaths.has(path.split(/[?#]/)[0]) ? path : '/';
}

function SessionStatus() {
  const { status, error, retry } = useAuth();
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-6 text-foreground">
      <div className="max-w-sm text-center" aria-live="polite">
        {status === 'error' ? (
          <>
            <h1 className="text-lg font-medium tracking-tight">We couldn’t open your workspace</h1>
            <p className="mt-3 text-sm leading-6 text-muted">{error}</p>
            <Button className="mt-6" onClick={retry}>Try again</Button>
          </>
        ) : (
          <>
            <Spinner className="mx-auto text-accent" label="Restoring your session" />
            <p className="mt-4 text-sm text-muted">Opening your workspace…</p>
          </>
        )}
      </div>
    </main>
  );
}

export function RequireAuth() {
  const { status, identity } = useAuth();
  const location = useLocation();
  if (status === 'loading' || status === 'error') return <SessionStatus />;
  if (status === 'anonymous') return <Navigate replace to="/login" state={{ from: location.pathname + location.search + location.hash }} />;
  return <StudentProfileProvider key={identity?.learner_id}><Outlet /></StudentProfileProvider>;
}

export function RequireGuest() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading' || status === 'error') return <SessionStatus />;
  if (status === 'authenticated') return <Navigate replace to={returnPath(location.state)} />;
  return <Outlet />;
}
