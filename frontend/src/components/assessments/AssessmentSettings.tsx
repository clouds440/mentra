import { useEffect, useState } from 'react';
import { Toggle } from '../ui/Toggle';
import { assessments } from '../../services/assessments';

export function AssessmentSettings() {
  const [value, setValue] = useState<{ auto_add: boolean; revision: number }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void assessments.preferences(controller.signal).then(result => { if (!controller.signal.aborted) setValue(result); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load assessment settings.'); });
    return () => controller.abort();
  }, [reload]);
  async function change(auto: boolean) {
    if (!value) return; const previous=value; setValue({...value,auto_add:auto}); setBusy(true); setError('');
    try { setValue(await assessments.savePreferences(auto, value.revision, new AbortController().signal)); }
    catch (reason) { setValue(previous); setError(reason instanceof Error ? reason.message : 'Unable to save assessment settings.'); }
    finally { setBusy(false); }
  }
  return <section className="mt-6 space-y-3 border-t border-border pt-6">
    <h2 className="text-sm font-medium text-heading">Assessments in chat</h2>
    <Toggle label="Always auto add assessments" checked={value?.auto_add ?? false} disabled={!value || busy} onChange={event => void change(event.target.checked)} />
    <p className="text-sm text-muted">Save every quiz or mock paper generated in chat to your Assessments library. With this off, practice stays in its chat until you add it or ask to evaluate your answers.</p>
    {error && <p role="alert" className="text-sm text-danger">{error} <button className="underline" disabled={busy} onClick={() => { setError(''); setReload(value => value+1); }}>Refresh</button></p>}
  </section>;
}
