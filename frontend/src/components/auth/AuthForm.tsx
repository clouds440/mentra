import { Eye, EyeOff, ArrowRight } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Button, Card, Input, Spinner } from '../ui';
import { useAuth } from './AuthProvider';
import { ApiError } from '../../services/api';
import { authErrorMessage } from '../../services/auth';

type FieldErrors = Partial<Record<'username' | 'password', string>>;

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const registration = mode === 'register';
  const auth = useAuth();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const normalizedUsername = username.trim().toLowerCase();
    const issues: FieldErrors = {};
    if (!/^[a-z0-9][a-z0-9_.-]{2,63}$/.test(normalizedUsername)) {
      issues.username = 'Use 3–64 letters, numbers, dots, underscores, or hyphens.';
    }
    if (password.length < (registration ? 12 : 1)) {
      issues.password = registration ? 'Use at least 12 characters for your password.' : 'Enter your password.';
    } else if (password.length > 256) {
      issues.password = 'Use no more than 256 characters.';
    }
    setFields(issues);
    setError(null);
    if (Object.keys(issues).length) {
      const field = issues.username ? 'username' : 'password';
      event.currentTarget.querySelector<HTMLInputElement>(`[name="${field}"]`)?.focus();
      return;
    }
    setSubmitting(true);
    try {
      await auth[mode]({ username: normalizedUsername, password });
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === 'ACCOUNT_EXISTS') {
        setFields({ username: failure.message });
      } else if (failure instanceof ApiError && failure.status === 422 && failure.details.length) {
        const backendFields: FieldErrors = {};
        for (const issue of failure.details) {
          const field = issue.location[issue.location.length - 1];
          if (field === 'username' || field === 'password') backendFields[field] = issue.message.replace(/^Value error, /, '');
        }
        setFields(backendFields);
        setError(Object.keys(backendFields).length ? null : authErrorMessage(failure));
      } else {
        setError(authErrorMessage(failure));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="auth-enter rounded-2xl p-6 shadow-lg shadow-shadow/5 backdrop-blur-none sm:p-8">
      <div className="mb-7">
        <h1 className="text-2xl font-medium tracking-tight text-foreground">
          {registration ? 'Create your account' : 'Welcome back'}
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          {registration ? 'Create your Mentra account to get started.' : 'Sign in to your Mentra workspace.'}
        </p>
      </div>

      <form aria-label={registration ? 'Create account' : 'Sign in'} aria-busy={submitting} noValidate onSubmit={submit}>
        {error && <p role="alert" className="mb-5 rounded-xl border border-danger/20 bg-danger/5 px-4 py-3 text-sm leading-5 text-danger">{error}</p>}
        <div className="space-y-5">
          <div>
            <label className="mb-2 block text-sm font-medium text-heading" htmlFor="username">Username</label>
            <Input id="username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
              className="min-h-12 text-sm" maxLength={64} required value={username} disabled={submitting}
              aria-invalid={Boolean(fields.username)} aria-describedby={fields.username ? 'username-error' : registration ? 'username-hint' : undefined}
              onChange={(event) => { setUsername(event.target.value); setFields((current) => ({ ...current, username: undefined })); setError(null); }} />
            {fields.username ? <p id="username-error" role="alert" className="mt-2 text-xs leading-5 text-danger">{fields.username}</p>
              : registration && <p id="username-hint" className="mt-2 text-xs leading-5 text-subtle">Letters, numbers, dots, underscores, or hyphens.</p>}
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-heading" htmlFor="password">Password</label>
            <div className="relative">
              <Input id="password" name="password" type={visible ? 'text' : 'password'}
                autoComplete={registration ? 'new-password' : 'current-password'} className="min-h-12 pr-12 text-sm"
                minLength={registration ? 12 : 1} maxLength={256} required value={password} disabled={submitting}
                aria-invalid={Boolean(fields.password)} aria-describedby={fields.password ? 'password-error' : registration ? 'password-hint' : undefined}
                onChange={(event) => { setPassword(event.target.value); setFields((current) => ({ ...current, password: undefined })); setError(null); }} />
              <button aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible}
                className="absolute inset-y-1 right-1 grid w-10 place-items-center rounded-lg text-subtle hover:bg-hover hover:text-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
                disabled={submitting} onClick={() => setVisible((value) => !value)} type="button">
                {visible ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}
              </button>
            </div>
            {fields.password ? <p id="password-error" role="alert" className="mt-2 text-xs leading-5 text-danger">{fields.password}</p>
              : registration && <p id="password-hint" className="mt-2 text-xs leading-5 text-subtle">Use at least 12 characters.</p>}
          </div>
        </div>
        <Button className="mt-7 min-h-12 w-full" disabled={submitting} type="submit">
          {submitting ? <><Spinner className="h-4 w-4" label={registration ? 'Creating account' : 'Signing in'} />{registration ? 'Creating account…' : 'Signing in…'}</>
            : <>{registration ? 'Create account' : 'Sign in'}<ArrowRight aria-hidden="true" size={16} /></>}
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        {registration ? 'Already have an account?' : 'New to Mentra?'}{' '}
        <Link className="rounded text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          state={location.state} to={registration ? '/login' : '/register'}>
          {registration ? 'Sign in' : 'Create an account'}
        </Link>
      </p>
    </Card>
  );
}
