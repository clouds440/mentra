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
  const [saved, setSaved] = useState(false);
  const active = useRef<AbortController | null>(null);
  async function load() {
    active.current?.abort(); const controller = new AbortController(); active.current = controller;
    setBusy(true); setError('');
    try { const result = await notifications.preferences(controller.signal); if (!controller.signal.aborted) setValue(result); }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load settings.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  useEffect(() => { void load(); return () => active.current?.abort(); }, []);
  async function save() {
    if (!value || busy) return;
    const controller = new AbortController(); active.current = controller; setBusy(true); setError('');
    try { const result = await notifications.savePreferences(value, controller.signal); if (!controller.signal.aborted) { setValue(result); setSaved(true); notificationChanged(); } }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to save settings.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="space-y-5 py-7"><h2 className="text-lg font-medium">Notifications</h2><p className="text-sm text-muted">Each event can send one reminder. Reminders missed while notifications are disabled are not sent later.</p>
    {error && <p role="alert" className="text-sm text-danger">{error} <button className="underline" onClick={() => void load()}>Reload settings</button></p>}
    {!value && busy && <p role="status">Loading notification settings…</p>}
    {value && <><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={value.enabled} disabled={busy} onChange={event => { setSaved(false); setValue({ ...value, enabled: event.target.checked }); }} />Enable notifications</label>
      <label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={!value.disabled_kinds.includes('event_reminder')} disabled={busy} onChange={event => { setSaved(false); setValue({ ...value, disabled_kinds: event.target.checked ? value.disabled_kinds.filter(kind => kind !== 'event_reminder') : [...value.disabled_kinds, 'event_reminder'] }); }} />Event reminders</label>
      <Button disabled={busy} onClick={() => void save()}>{busy ? 'Saving…' : 'Save settings'}</Button>{saved && <p role="status" className="text-sm text-muted">Settings saved.</p>}</>}
  </section>;
}
