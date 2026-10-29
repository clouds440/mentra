import { PageSection } from '../workspace/PageShell';
import { buttonStyles } from '../ui/Button';
import { usePageRefresh, refreshPage } from '../../hooks/usePageRefresh';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { Toggle } from '../ui/Toggle';
import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { Button } from '../ui/Button';
import { notifications, notificationChanged } from '../../services/notifications';
import type { NotificationPreferences } from '../../types/notifications';

export function NotificationSettings() {
  const { identity } = useAuth();
  return <Preferences key={identity?.learner_id} />;
}
function Preferences() {
  const [value, setValue] = useState<NotificationPreferences | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const active = useRef<AbortController | null>(null);
  async function load() {
    active.current?.abort(); const controller = new AbortController(); active.current = controller;
    setBusy(true); setError('');
    try { const result = await notifications.preferences(controller.signal); if (!controller.signal.aborted) setValue(result); }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load settings.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  usePageRefresh(() => { void load(); }, !busy && !dirty, ['notifications']);
  useEffect(() => { void load(); return () => active.current?.abort(); }, []);
  async function save() {
    if (!value || busy) return;
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try { const result = await notifications.savePreferences(value, controller.signal); if (!controller.signal.aborted) { setValue(result); setDirty(false); setSaved(true); notificationChanged(); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to save settings.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <PageSection className="workspace-panel space-y-5"><h2 className="text-lg font-medium">Notifications</h2><p className="text-sm text-muted">Each event can send one reminder. Reminders missed while notifications are disabled are not sent later.</p>
    {error && <p role="alert" className="text-sm text-danger">{error} <button type="button" className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'ml-2 mt-1' })} onClick={() => refreshPage(() => { void load(); })}>Reload settings</button></p>}
    {!value && busy && <Skeleton variant="form" />}
    {value && <><Toggle label="Enable notifications" checked={value.enabled} disabled={busy} onChange={event => { setDirty(true); setSaved(false); setValue({ ...value, enabled: event.target.checked }); }} />
      <Toggle label="Event reminders" checked={!value.disabled_kinds.includes('event_reminder')} disabled={busy} onChange={event => { setDirty(true); setSaved(false); setValue({ ...value, disabled_kinds: event.target.checked ? value.disabled_kinds.filter(kind => kind !== 'event_reminder') : [...value.disabled_kinds, 'event_reminder'] }); }} />
      <Button disabled={busy} loading={busy} onClick={() => void save()}>{'Save settings'}</Button><p role="status" className="min-h-5 text-sm text-muted">{saved ? 'Settings saved.' : ''}</p></>}
  </PageSection>;
}
