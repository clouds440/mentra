import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useSidePanelActions } from '../workspace/sidePanelState';
import { usePageRefresh } from '../../hooks/usePageRefresh';
import { invalidatePageCache } from '../../services/pageCache';
import { getMaterial, materialError, pendingJob } from '../../services/rag';
import { ApiError } from '../../services/api';
import type { MaterialDocument, MaterialVersion } from '../../types/rag';
import { Button, buttonStyles, Skeleton } from '../ui';
import { Toggle } from '../ui/Toggle';
import { SourceReader, type SourceStatus } from './SourceViewer';

export function MaterialSourceTab({ initial, version, archivedContext = false, allowArchived = false }: {
  initial: MaterialDocument; version?: MaterialVersion; archivedContext?: boolean; allowArchived?: boolean;
}) {
  const panel = useSidePanelActions();
  const [doc, setDoc] = useState(initial);
  const [selected, setSelected] = useState(version ?? initial.versions?.[0]);
  const [consent, setConsent] = useState(allowArchived);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  usePageRefresh(refresh, true, ['documents', 'learning-contexts']);
  const current = doc.versions?.find(item => item.id === selected?.id) ?? selected;
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let processing = !!pendingJob(initial) || (version ?? initial.versions?.[0])?.extraction_state === 'processing';
    let retries = 0;
    async function load() {
      try {
        // A retained tab can outlive deletion, archival, or reindexing of its source.
        const value = await getMaterial(initial.id, controller.signal, true);
        if (controller.signal.aborted) return;
        retries = 0;
        setError(''); setLoaded(true); setUnavailable(false); setDoc(value);
        setSelected(current => current ?? value.versions?.[0]);
        const liveVersion = value.versions?.find(item => item.id === version?.id) ?? (version ? undefined : value.versions?.[0]);
        processing = !!pendingJob(value) || liveVersion?.extraction_state === 'processing';
        if (processing) timer = setTimeout(load, 3000);
      } catch (reason) {
        if (controller.signal.aborted) return;
        const terminal = reason instanceof ApiError && [401, 403, 404, 410].includes(reason.status);
        setError(materialError(reason));
        if (terminal) setUnavailable(true);
        if (processing && !terminal && retries++ < 3) timer = setTimeout(load, 3000);
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [initial, version, revision]);

  const generationIds = new Set(doc.generations?.filter(item => item.version_id === current?.id).map(item => item.id));
  const job = doc.jobs.find(item => item.operation === 'INGEST' && generationIds.has(item.generation_id ?? ''));
  const status: SourceStatus = { state: current?.extraction_state ?? (current?.generation_id ? 'ready'
    : job && ['QUEUED', 'RUNNING', 'RETRY_WAIT'].includes(job.state) ? 'processing'
    : job?.state === 'FAILED' ? 'failed' : 'unavailable'), error: current?.extraction_error ?? job?.error };
  return <>
    <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-3">
      <Link onClick={panel?.hide} className={buttonStyles({ size: 'sm', variant: 'ghost' })} to={'/library/' + encodeURIComponent(doc.id)}>Manage material</Link>
      {(doc.archived || archivedContext) && <Toggle label="Allow viewing archived source material" checked={consent} onCheckedChange={checked => setConsent(checked)} />}
    </div>
    {error && <p role="alert" className="px-4 py-3 text-sm text-danger">{error} <Button size="sm" variant="ghost" onClick={refresh}>Retry</Button></p>}
    {loaded && !unavailable && current ? <SourceReader key={current.id + ':' + consent} filename={current.filename} includeArchived={consent} status={status}
        onRefresh={() => { invalidatePageCache(['documents']); refresh(); }}
        source={{ token: '', document_id: doc.id, version_id: current.id, generation_id: current.generation_id ?? '', chunk_id: '',
          title: doc.title, heading_path: [], spans: [], excerpt: '', warnings: current.warnings ?? [] }} />
      : error ? null : loaded ? <p className="p-4 text-sm text-muted">A source version will appear here when the upload is available.</p>
      : <Skeleton variant="text" rows={5} className="p-4" />}
  </>;
}
