import { useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Sparkles } from 'lucide-react';
import mentraLogo from '../assets/mentra-logo.png';
import { Button, Card, Spinner } from '../components/ui';
import { ProfileForm } from '../components/student-profile/ProfileForm';
import { ProfileEstimates } from '../components/student-profile/ProfileEstimates';
import { CalibrationAssessment } from '../components/student-profile/CalibrationAssessment';
import { useStudentProfile } from '../components/student-profile/StudentProfileProvider';
import { LogoutButton } from '../components/auth/LogoutButton';
import { returnPath } from '../components/auth/AuthRoutes';
import { ThemeSelector } from '../components/theme/ThemeSelector';
import * as profileApi from '../services/studentProfile';
import type { CalibrationAttempt, StudentProfile } from '../types/studentProfile';

export function OnboardingPage({ calibrationOnly = false }: { calibrationOnly?: boolean }) {
  const { profile, replace, refresh } = useStudentProfile();
  const location = useLocation();
  const navigate = useNavigate();
  const [attempt, setAttempt] = useState<CalibrationAttempt | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState<StudentProfile | null>(null);
  const target = calibrationOnly ? '/settings' : returnPath(location.state);
  const hasDetails = Boolean(profile?.details);
  const contextVersion = profile?.context_version;
  useEffect(() => {
    if (!hasDetails) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError(null); setAttempt(null);
    void profileApi.getCalibration(controller.signal).then((current) => {
      if (!controller.signal.aborted) setAttempt(current);
    }).catch((failure) => { if (!controller.signal.aborted) setError(profileApi.profileError(failure)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [hasDetails, contextVersion]);
  if (!profile) return null;
  if (!calibrationOnly && profile.onboarding_phase === 'complete' && !finished) return <Navigate replace to={target} />;
  if (calibrationOnly && !profile.details) return <Navigate replace to="/onboarding" state={{ from: '/settings' }} />;
  async function start() {
    setPending(true); setError(null);
    try { const current = await profileApi.startCalibration(); setAttempt(current); await refresh(); }
    catch (failure) { setError(profileApi.profileError(failure)); }
    finally { setPending(false); }
  }
  async function skip() {
    if (!profile || pending) return;
    setPending(true); setError(null);
    try { replace(await profileApi.skipCalibration(profile.version)); navigate(target, { replace: true }); }
    catch (failure) { setError(profileApi.profileError(failure)); await refresh().catch(() => {}); }
    finally { setPending(false); }
  }
  function complete(next: StudentProfile) { setFinished(next); replace(next); }
  const results = finished ? profile : attempt?.status === 'completed' ? profile : null;
  return <main className="min-h-dvh bg-background px-5 py-6 text-foreground sm:px-6 sm:py-10">
    <div className="mx-auto w-full max-w-xl">
      <header className="mb-7 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5"><img src={mentraLogo} alt="" aria-hidden="true" className="h-8 w-8 object-contain" /><span className="text-lg font-semibold tracking-tight">mentra</span></div>
        <div className="w-28"><LogoutButton /></div>
      </header>
      <Card className="auth-enter rounded-2xl p-6 shadow-lg shadow-shadow/5 backdrop-blur-none sm:p-8">
        {!hasDetails ? <><p className="text-xs font-medium uppercase tracking-wider text-accent">Step 1 of 2 · Your profile</p>
          <h1 className="mt-3 text-2xl font-medium tracking-tight">Make Mentra yours</h1>
          <p className="mb-7 mt-2 text-sm leading-6 text-muted">Tell Mentra a little about you. These details help it teach at the right level, and you can edit them later.</p>
          <ProfileForm /></>
          : results ? <><p className="text-xs font-medium uppercase tracking-wider text-accent">Calibration complete</p>
            <h1 className="mt-3 text-2xl font-medium tracking-tight">{results.evaluation_status === 'applied' ? 'Your starting point is ready' : 'Your answers are saved'}</h1>
            <p className="mt-2 text-sm leading-6 text-muted">{results.evaluation_status === 'applied' ? 'Mentra will refine these early signals as it gathers evidence.' : 'Your answers are saved. You can enter Mentra while AI evaluation is unavailable.'}</p>
            <div className="mt-7"><ProfileEstimates profile={results} /></div>
            <Button className="mt-7 w-full" onClick={() => navigate(target, { replace: true })}>{calibrationOnly ? 'Back to settings' : 'Enter Mentra'}<ArrowRight aria-hidden="true" size={16} /></Button></>
            : loading ? <div className="py-12 text-center"><Spinner className="mx-auto text-accent" label="Restoring your calibration" /><p className="mt-4 text-sm text-muted">Restoring your progress…</p></div>
              : attempt?.status === 'in_progress' ? <CalibrationAssessment key={attempt.id} initialAttempt={attempt} onComplete={complete} onSkip={() => { void skip(); }} />
                : <><p className="text-xs font-medium uppercase tracking-wider text-accent">{calibrationOnly ? 'Personalization' : 'Step 2 of 2'} · Recommended</p>
                  <span className="mt-6 grid h-10 w-10 place-items-center rounded-xl bg-active text-accent"><Sparkles aria-hidden="true" size={20} /></span>
                  <h1 className="mt-4 text-2xl font-medium tracking-tight">A quick starting point</h1>
                  <p className="mt-3 text-sm leading-6 text-muted">Eight quick questions help Mentra match explanations to you. They cover reasoning, understanding, and level-appropriate problem solving.</p>
                  <p className="mt-3 text-sm leading-6 text-muted">About 1–2 minutes. No grades, no pressure. We recommend completing it for better personalization.</p>
                  <Button className="mt-7 w-full" disabled={pending || Boolean(error)} onClick={() => { void start(); }}>{pending && <Spinner className="h-4 w-4" label="Starting calibration" />}Start quick calibration<ArrowRight aria-hidden="true" size={16} /></Button>
                  <Button className="mt-3 w-full" variant="ghost" disabled={pending} onClick={() => { void skip(); }}>Skip for now</Button>
                  <p className="mt-3 text-center text-xs leading-5 text-subtle">Skipping leaves your starting estimates unknown. You can calibrate later in Settings.</p></>}
        {error && <div className="mt-5" role="alert"><p className="text-sm text-danger">{error}</p>
          <Button className="mt-3" size="sm" variant="secondary" onClick={() => { window.location.reload(); }}>Reload</Button></div>}
        {calibrationOnly && !results && !attempt && <Button className="mt-3 w-full" variant="ghost" onClick={() => navigate('/settings')}>Back to settings</Button>}
      </Card>
      <div className="mx-auto mt-6 max-w-xs"><ThemeSelector collapsed={false} /></div>
    </div>
  </main>;
}
