import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { Button, Spinner } from '../ui';
import { useStudentProfile } from './StudentProfileProvider';
import { LogoutButton } from '../auth/LogoutButton';

export function ProfileReady() {
  const { profile, error, refresh } = useStudentProfile();
  if (profile) return <Outlet />;
  return <main className="flex min-h-dvh items-center justify-center bg-background px-6 text-foreground">
    <div className="max-w-sm text-center" aria-live="polite">
      {error ? <><h1 className="text-lg font-medium">We couldn’t load your profile</h1>
        <p className="mt-3 text-sm leading-6 text-muted">{error}</p>
        <Button className="mt-6" onClick={() => { void refresh().catch(() => {}); }}>Try again</Button>
        <div className="mx-auto mt-4 w-28"><LogoutButton /></div></>
        : <><Spinner className="mx-auto text-accent" label="Loading your profile" /><p className="mt-4 text-sm text-muted">Opening your workspace…</p></>}
    </div>
  </main>;
}

export function RequireOnboardingComplete() {
  const { profile } = useStudentProfile();
  const location = useLocation();
  if (profile?.onboarding_phase !== 'complete') return <Navigate replace to="/onboarding"
    state={{ from: location.pathname + location.search + location.hash }} />;
  return <Outlet />;
}
