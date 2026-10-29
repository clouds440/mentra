import { PageSection } from '../workspace/PageShell';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useAuth } from './AuthProvider';
import { changePassword } from '../../services/auth';
import { ApiError } from '../../services/api';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

export function PasswordSettings() {
  const { identity } = useAuth();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const submitting = useRef(false);
  const oldInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!busy && error === 'Your current password is incorrect.') oldInput.current?.focus();
  }, [busy, error]);

  if (!identity?.user_id || identity.provider) return null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await changePassword(oldPassword, newPassword);
      setOldPassword('');
      setNewPassword('');
      setSaved(true);
    } catch (failure) {
      setError(failure instanceof ApiError
        ? failure.status === 401 ? 'Your session has expired. Sign in again to change your password.'
          : failure.status === 422 ? 'Use 12–256 characters for your new password.' : failure.message
        : 'Couldn’t change your password. Please try again.');
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return <PageSection className="workspace-panel mt-6" aria-labelledby="password-settings-heading">
    <h2 id="password-settings-heading" className="text-lg font-medium tracking-tight text-heading">Change password</h2>
    <p id="password-settings-description" className="mt-2 text-sm leading-6 text-muted">Enter your current password to choose a new one. Other sessions will be signed out.</p>
    <form onSubmit={submit} aria-describedby="password-settings-description" className="mt-5 max-w-md space-y-4" onChange={() => { setSaved(false); setError(null); }}>
      <input type="text" name="username" autoComplete="username" value={identity.username ?? ''} readOnly hidden />
      <div className="space-y-2">
        <label htmlFor="current-password" className="block text-sm font-medium text-heading">Current password</label>
        <Input ref={oldInput} id="current-password" name="old_password" type="password" autoComplete="current-password" required maxLength={256}
          value={oldPassword} onChange={event => setOldPassword(event.target.value)} disabled={busy} />
      </div>
      <div className="space-y-2">
        <label htmlFor="new-password" className="block text-sm font-medium text-heading">New password</label>
        <Input id="new-password" name="new_password" type="password" autoComplete="new-password" required minLength={12} maxLength={256}
          aria-describedby="new-password-help" value={newPassword} onChange={event => setNewPassword(event.target.value)} disabled={busy} />
        <p id="new-password-help" className="text-xs text-subtle">Use at least 12 characters.</p>
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <p role="status" className="min-h-5 text-sm text-body">{saved ? 'Password changed. Use your new password next time you sign in.' : ''}</p>
      <Button type="submit" loading={busy}>Change password</Button>
    </form>
  </PageSection>;
}
