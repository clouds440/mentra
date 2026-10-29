import { WorkspaceHeader } from '../components/workspace/WorkspaceHeader';
import { FileText } from 'lucide-react';
import { PageShell } from '../components/workspace/PageShell';
import { invalidatePageCache } from '../services/pageCache';
import { practiceLink } from '../services/practiceIntent';
import { Dialog } from '../components/ui/Dialog';
import { materialWarningMessage } from '../services/userError';
import { usePendingWork, usePageRefresh } from '../hooks/usePageRefresh';
import { Skeleton } from '../components/ui/Skeleton';
import { Toggle } from '../components/ui/Toggle';
import { useCallback, useEffect, useRef, useState } from 'react';

import { Link, useNavigate, useParams } from 'react-router-dom';
import { Button, Input, Select, FormField, buttonStyles } from '../components/ui';
import { MaterialUpload } from '../components/library/MaterialUpload';
import { SourceViewer } from '../components/library/SourceViewer';
import { getMaterial, getCapabilities, listContexts, listVersions, updateMaterial, deleteMaterial, reindexMaterial, retryJob, pendingJob, materialError, tagMaterial } from '../services/rag';
import type { LearningContext, MaterialDocument, MaterialVersion, RAGCapabilities, SourceReference } from '../types/rag';

export function MaterialDetailPage() {
  const { documentId = '' } = useParams(); const navigate = useNavigate();
  const [doc, setDoc] = useState<MaterialDocument>(); const [contexts, setContexts] = useState<LearningContext[]>([]);
  const [caps, setCaps] = useState<RAGCapabilities>(); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState(''); const [selection, setSelection] = useState<string[]>([]);
  const [source, setSource] = useState<SourceReference>(); const [reload, setReload] = useState(0); const [consent, setConsent] = useState(false);
  const [conceptLabels, setConceptLabels] = useState(''); const [tagNotice, setTagNotice] = useState('');
  const [olderVersions, setOlderVersions] = useState<MaterialVersion[]>([]); const [loadingVersions, setLoadingVersions] = useState(false);
  const controllerRef = useRef<AbortController>();
  const deleteDialog = useRef<HTMLDialogElement>(null); const revision = useRef('');
  const dirty = useRef(false);
  const latestDocument = useRef<MaterialDocument>();
  const [conflict, setConflict] = useState(false);
  const [activeAction, setActiveAction] = useState('');
  const processing = useRef(false);
  const request = useRef<AbortController>();
  const refresh = useCallback(() => setReload(v => v + 1), []);
  usePageRefresh(() => { if (!request.current) refresh(); }, true, ['documents', 'learning-contexts']);
  usePendingWork(() => { if (!request.current) refresh(); }, !busy && !!doc && !!pendingJob(doc));
  useEffect(() => {
    const abort = new AbortController();
    controllerRef.current = abort; request.current = abort;
    async function load() {
      try {
        const [data, ctx, capabilities] = await Promise.all([getMaterial(documentId, abort.signal), listContexts(abort.signal), getCapabilities(abort.signal)]);
        if (abort.signal.aborted) return;
        const isProcessing = !!pendingJob(data);
        if (processing.current && !isProcessing) invalidatePageCache(['documents', 'learning'], true);
        processing.current = isProcessing;
        latestDocument.current = data; setContexts(ctx); setCaps(capabilities);
        if (dirty.current && revision.current !== `${data.id}:${data.revision}`) setConflict(true);
        else {
          setDoc(data);
          if (revision.current !== `${data.id}:${data.revision}`) { revision.current = `${data.id}:${data.revision}`; setTitle(data.title); setSelection(data.context_ids); setOlderVersions([]); setConflict(false); }
        }
      } catch (e) { if (!abort.signal.aborted) setError(materialError(e)); }
      finally { if (request.current === abort) request.current = undefined; }
    }
    void load(); return () => { abort.abort(); if (request.current === abort) request.current = undefined; };
  }, [documentId, reload]);
  useEffect(() => { setSource(undefined); setOlderVersions([]); setConsent(false); }, [documentId]);
  async function action(name: string, work: () => Promise<unknown>) { if (busy) return; setBusy(true); setActiveAction(name); setError(''); try { await work(); if (name === 'save') dirty.current = false; refresh(); } catch (e) { setError(materialError(e)); refresh(); } finally { setBusy(false); setActiveAction(''); } }
  function reloadSaved() {
    const data = latestDocument.current; if (!data) return;
    dirty.current = false; setConflict(false); setDoc(data); revision.current = `${data.id}:${data.revision}`; setTitle(data.title); setSelection(data.context_ids);
  }
  async function loadVersions() {
    if (!doc) return;
    const controller = controllerRef.current; setLoadingVersions(true);
    try {
      const page = await listVersions(doc.id, doc.versions.length + olderVersions.length, controller?.signal);
      if (!controller?.signal.aborted) setOlderVersions(previous => [...previous, ...page.items]);
    } catch (e) { if (!controller?.signal.aborted) setError(materialError(e)); }
    finally { if (!controller?.signal.aborted) setLoadingVersions(false); }
  }
  if (!doc || doc.id !== documentId) return <PageShell><WorkspaceHeader title="Material" description="Your source, details and versions." icon={FileText} /><Link to="/library" className="text-accent">Back to Library</Link>{error ? <p role="alert" className="mt-4 text-danger">{error}</p> : <Skeleton variant="form" />}</PageShell>;
  const job = pendingJob(doc); const active = doc.generations.find(g => g.id === doc.active_generation_id);
  const versions = [...doc.versions, ...olderVersions];
  function openVersion(versionId: string) {
    if (!doc) return;
    const version = versions.find(v => v.id === versionId);
    setSource({ token: '', document_id: doc.id, version_id: versionId, generation_id: version?.generation_id ?? '', chunk_id: '', title: doc.title, heading_path: [], spans: [], excerpt: '', warnings: version?.warnings ?? [] });
  }
  return <PageShell>
    <Link to="/library" className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'w-fit' })}>Back to Library</Link><WorkspaceHeader title={doc.title} description={doc.archived ? 'Archived material' : active ? 'Ready to study - Source details and versions' : 'Preparing your study source'} icon={FileText} actions={<>{active && !doc.archived && <Link to={`/?document=${doc.id}`} className={buttonStyles({ variant: 'secondary' })}>Study in chat</Link>}{active && !doc.archived && <Link to={practiceLink({ document_ids: [doc.id], context_id: contexts.find(item => doc.context_ids.includes(item.context_id) && item.status !== 'ARCHIVED')?.context_id, topic: doc.title })} className={buttonStyles({ variant: 'secondary' })}>Quiz this material</Link>}</>} />
    {conflict && <div role="alert" className="inline-notice">Saved details changed while you were editing. Your draft is preserved. <Button size="sm" variant="secondary" onClick={reloadSaved}>Reload saved details</Button></div>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}{active?.warnings.map(w => <p key={w} className="text-sm text-muted">{materialWarningMessage(w)}</p>)}
    {doc.jobs.filter(j => j.state === 'FAILED').slice(0, 1).map(j => <div key={j.id} className="rounded-xl border border-border p-4"><p className="text-sm text-danger">This material could not be processed.</p><Button className="mt-3" variant="secondary" disabled={busy} loading={activeAction === 'retry'} onClick={() => void action('retry', () => retryJob(j.id))}>Retry processing</Button></div>)}
    <form className="workspace-panel space-y-4" onSubmit={e => { e.preventDefault(); void action('save', () => updateMaterial(doc, { title, context_ids: selection })); }}>
      <FormField label="Title">{field => <Input {...field} value={title} maxLength={200} required onChange={e => { dirty.current = true; setTitle(e.target.value); }} />}</FormField>
      <label className="block text-sm">Associated contexts<Select multiple className="mt-2" value={selection} onChange={e => { dirty.current = true; setSelection(Array.from(e.target.selectedOptions, o => o.value)); }}>{contexts.filter(c => c.status !== 'ARCHIVED' || selection.includes(c.context_id)).map(c => <option key={c.context_id} value={c.context_id}>{c.name} ({c.status.toLowerCase()})</option>)}</Select></label>
      <Button type="submit" disabled={busy || conflict || !selection.length} loading={activeAction === 'save'}>Save material details</Button>
    </form>
    <div className="action-row border-b border-border pb-4"><Button variant="secondary" disabled={busy || !!job} loading={activeAction === 'archive'} onClick={() => void action('archive', () => updateMaterial(doc, { archived: !doc.archived }))}>{doc.archived ? 'Unarchive material' : 'Archive material'}</Button><Button variant="secondary" disabled={busy || !!job || doc.archived} loading={activeAction === 'reindex'} onClick={() => void action('reindex', () => reindexMaterial(doc))}>Reindex material</Button><Button variant="danger" disabled={busy} onClick={() => deleteDialog.current?.showModal()}>Delete material</Button></div>
    <form className="workspace-panel space-y-3" onSubmit={e => { e.preventDefault(); void action('tags', async () => { const result = await tagMaterial(doc, conceptLabels.split(',').map(s => s.trim()).filter(Boolean)); setTagNotice(result.unresolved_labels.length ? `No canonical match for: ${result.unresolved_labels.join(', ')}. These labels were not attached.` : 'Canonical concept tags updated.'); }); }}><label className="block text-sm">Concept tags<Input className="mt-2" value={conceptLabels} onChange={e => setConceptLabels(e.target.value)} placeholder="Known concept names, separated by commas" /></label><p className="text-xs text-muted">Only concepts already recognized by Mentra can be attached. This does not change your learning estimates.</p><Button disabled={busy || !!job} loading={activeAction === 'tags'} variant="secondary" type="submit">Resolve concept tags</Button>{tagNotice && <p role="status" className="text-sm text-muted">{tagNotice}</p>}</form>
    <section><h2 className="font-medium">Source versions</h2>{(doc.archived || contexts.some(c => doc.context_ids.includes(c.context_id) && c.status === 'ARCHIVED')) && <Toggle className="mt-3" label="Allow viewing archived source material" checked={consent} onChange={e => setConsent(e.target.checked)} />}<ul className="mt-3 space-y-2">{versions.map((v, index) => <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border p-4 text-sm"><span>{v.filename} · {Math.ceil(v.size_bytes / 1024)} KiB {index === 0 ? '· Latest upload' : '· Earlier version'}</span><Button size="sm" variant="secondary" onClick={() => openVersion(v.id)}>Open source version</Button></li>)}</ul>{versions.length < doc.version_count && <Button className="mt-3" variant="secondary" disabled={loadingVersions} loading={loadingVersions} onClick={() => void loadVersions()}>{'Load earlier versions'}</Button>}</section>
    {caps && !doc.archived && <MaterialUpload contexts={contexts} capabilities={caps} replacement={doc} onContextCreated={refresh} onAccepted={() => refresh()} />}
    {source && <SourceViewer source={source} filename={versions.find(v => v.id === source.version_id)?.filename} includeArchived={consent} onClose={() => setSource(undefined)} />}
    <Dialog busy={busy} ref={deleteDialog} aria-label="Delete material confirmation" className="max-w-md"><h2 className="font-medium">Delete {doc.title}?</h2><p className="mt-3 text-sm text-muted">This removes the material and its source versions. It stops appearing in chat immediately after the request is accepted; storage cleanup may take longer.</p><div className="mt-5 flex gap-3"><Button variant="secondary" onClick={() => deleteDialog.current?.close()}>Keep material</Button><Button variant="danger" disabled={busy} loading={activeAction === 'delete'} onClick={() => void action('delete', async () => { await deleteMaterial(doc.id); deleteDialog.current?.close(); navigate('/library?deleted=1'); })}>Confirm deletion</Button></div></Dialog>
  </PageShell>;
}
