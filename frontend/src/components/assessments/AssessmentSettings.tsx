import { PageSection } from '../workspace/PageShell';
import { buttonStyles } from '../ui/Button';
import { usePageRefresh } from '../../hooks/usePageRefresh';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { useEffect, useState } from 'react';
import { Toggle } from '../ui/Toggle';
import { assessments } from '../../services/assessments';

export function AssessmentSettings() {
  const [value, setValue] = useState<{ auto_add: boolean; revision: number }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  usePageRefresh(() => setReload(value => value + 1), !busy, ['assessments']);
  useEffect(() => {
    const controller = new AbortController();
    void assessments.preferences(controller.signal).then(result => { if (!controller.signal.aborted) setValue(result); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to load assessment settings.'); });
    return () => controller.abort();
  }, [reload]);
  async function change(auto: boolean) {
    if (!value) return; const previous=value; setValue({...value,auto_add:auto}); setBusy(true); setError('');
    try { setValue(await assessments.savePreferences(auto, value.revision, new AbortController().signal)); }
    catch (reason) { setValue(previous); setError(reason instanceof ApiError ? reason.message : 'Unable to save assessment settings.'); }
    finally { setBusy(false); }
  }
  return <PageSection className="workspace-panel mt-6 space-y-3">
    <h2 className="text-sm font-medium text-heading">Assessments in chat</h2>
    {!value && !error ? <Skeleton variant="form" rows={1} /> : <Toggle label="Save chat assessments automatically" checked={value?.auto_add ?? false} disabled={!value || busy} onCheckedChange={checked => void change(checked)} />}
    <p className="text-sm text-muted">Keep quizzes and exam papers from chat in Assessments. When this is off, they stay in the conversation until you save them or ask Mentra to evaluate your answers.</p>
    {error && <p role="alert" className="text-sm text-danger">{error} <button type="button" className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'ml-2 mt-1' })} disabled={busy} onClick={() => { setError(''); setReload(value => value+1); }}>Refresh</button></p>}
  </PageSection>;
}
