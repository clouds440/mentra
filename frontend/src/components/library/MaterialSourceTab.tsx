import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSidePanelActions } from '../workspace/sidePanelState';
import { usePageRefresh, usePendingWork } from '../../hooks/usePageRefresh';
import { invalidatePageCache } from '../../services/pageCache';
import { getMaterial, materialError, pendingJob } from '../../services/rag';
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
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  usePageRefresh(refresh, true, ['documents', 'learning-contexts']);
  const current = doc.versions?.find(item => item.id === selected?.id) ?? selected;
  usePendingWork(refresh, !error && (!!pendingJob(doc) || current?.extraction_state === 'processing'));
  useEffect(() => {
    const controller = new AbortController();
    void getMaterial(initial.id, controller.signal, revision > 0).then(value => {
      if (controller.signal.aborted) return;
      setError(''); setLoaded(true); setDoc(value);
      setSelected(current => current ?? value.versions?.[0]);
    }).catch(reason => {
      if (!controller.signal.aborted) { setError(materialError(reason)); setLoaded(true); }
    });
    return () => controller.abort();
  }, [initial.id, revision]);

  const generationIds = new Set(doc.generations?.filter(item => item.version_id === current?.id).map(item => item.id));
  const job = doc.jobs.find(item => item.operation === 'INGEST' && generationIds.has(item.generation_id ?? ''));
  const status: SourceStatus = { state: current?.extraction_state ?? (current?.generation_id ? 'ready'
    : job && ['QUEUED', 'RUNNING', 'RETRY_WAIT'].includes(job.state) ? 'processing'
    : job?.state === 'FAILED' ? 'failed' : 'unavailable'), error: current?.extraction_error ?? job?.error };
  return <>
    <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-3">
      <Link onClick={panel?.hide} className={buttonStyles({ size: 'sm', variant: 'ghost' })} to={'/library/' + encodeURIComponent(doc.id)}>Manage material</Link>
      {(doc.archived || archivedContext) && <Toggle label="Allow viewing archived source material" checked={consent} onChange={event => setConsent(event.target.checked)} />}
    </div>
    {error ? <p role="alert" className="px-4 py-3 text-sm text-danger">{error} <Button size="sm" variant="ghost" onClick={refresh}>Retry</Button></p>
      : current ? <SourceReader filename={current.filename} includeArchived={consent} status={status}
        onRefresh={() => { invalidatePageCache(['documents']); refresh(); }}
        source={{ token: '', document_id: doc.id, version_id: current.id, generation_id: current.generation_id ?? '', chunk_id: '',
          title: doc.title, heading_path: [], spans: [], excerpt: '', warnings: current.warnings ?? [] }} />
      : loaded ? <p className="p-4 text-sm text-muted">A source version will appear here when the upload is available.</p>
      : <Skeleton variant="text" rows={5} className="p-4" />}
  </>;
}
