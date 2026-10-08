import { Toggle } from '../components/ui/Toggle';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Button, Input, Select, Spinner } from '../components/ui';
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
  const deleteDialog = useRef<HTMLDialogElement>(null); const revision = useRef(0);
  const refresh = useCallback(() => setReload(v => v + 1), []);
  useEffect(() => {
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    controllerRef.current = abort;
    async function load() {
      try {
        const [data, ctx, capabilities] = await Promise.all([getMaterial(documentId, abort.signal), listContexts(abort.signal), getCapabilities(abort.signal)]);
        if (abort.signal.aborted) return;
        setDoc(data); setContexts(ctx); setCaps(capabilities);
        if (revision.current !== data.revision) { revision.current = data.revision; setTitle(data.title); setSelection(data.context_ids); setOlderVersions([]); }
        if (pendingJob(data)) timer = setTimeout(() => { if (navigator.onLine && document.visibilityState === 'visible') void load(); }, 3000);
      } catch (e) { if (!abort.signal.aborted) setError(materialError(e)); }
    }
    void load(); const focus = () => { if (document.visibilityState === 'visible') { clearTimeout(timer); void load(); } };
    window.addEventListener('focus', focus); window.addEventListener('online', focus); document.addEventListener('visibilitychange', focus);
    return () => { abort.abort(); clearTimeout(timer); window.removeEventListener('focus', focus); window.removeEventListener('online', focus); document.removeEventListener('visibilitychange', focus); };
  }, [documentId, reload]);
  async function action(work: () => Promise<unknown>) { setBusy(true); setError(''); try { await work(); refresh(); } catch (e) { setError(materialError(e)); refresh(); } finally { setBusy(false); } }
  async function loadVersions() {
    if (!doc) return;
    const controller = controllerRef.current; setLoadingVersions(true);
    try {
      const page = await listVersions(doc.id, doc.versions.length + olderVersions.length, controller?.signal);
      if (!controller?.signal.aborted) setOlderVersions(previous => [...previous, ...page.items]);
    } catch (e) { if (!controller?.signal.aborted) setError(materialError(e)); }
    finally { if (!controller?.signal.aborted) setLoadingVersions(false); }
  }
  if (!doc) return <section className="p-6"><Link to="/library" className="text-accent">Back to Library</Link>{error ? <p role="alert" className="mt-4 text-danger">{error}</p> : <Spinner />}</section>;
  const job = pendingJob(doc); const active = doc.generations.find(g => g.id === doc.active_generation_id);
  const versions = [...doc.versions, ...olderVersions];
  function openVersion(versionId: string) {
    if (!doc) return;
    const version = versions.find(v => v.id === versionId);
    setSource({ token: '', document_id: doc.id, version_id: versionId, generation_id: version?.generation_id ?? '', chunk_id: '', title: doc.title, heading_path: [], spans: [], excerpt: '', warnings: version?.warnings ?? [] });
  }
  return <section className="mx-auto w-full max-w-4xl space-y-6 p-4 sm:p-8">
    <Link to="/library" className="text-sm text-accent">Back to Library</Link><div><h1 className="text-2xl font-medium">{doc.title}</h1><p className="mt-2 text-sm text-muted">{doc.archived ? 'Archived' : active ? 'Ready to study' : 'Not yet indexed'}{job ? ` · ${job.stage}` : ''}</p></div>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}{active?.warnings.map(w => <p key={w} className="text-sm text-muted">{w}</p>)}
    {doc.jobs.filter(j => j.state === 'FAILED').slice(0, 1).map(j => <div key={j.id} className="rounded-xl border border-border p-4"><p className="text-sm text-danger">{j.error}</p><Button className="mt-3" variant="secondary" disabled={busy} onClick={() => void action(() => retryJob(j.id))}>Retry processing</Button></div>)}
    <form className="space-y-4 rounded-xl border border-border p-5" onSubmit={e => { e.preventDefault(); void action(() => updateMaterial(doc, { title, context_ids: selection })); }}>
      <label className="block text-sm">Title<Input className="mt-2" value={title} maxLength={200} required onChange={e => setTitle(e.target.value)} /></label>
      <label className="block text-sm">Associated contexts<Select multiple className="mt-2" value={selection} onChange={e => setSelection(Array.from(e.target.selectedOptions, o => o.value))}>{contexts.filter(c => c.status !== 'ARCHIVED' || selection.includes(c.context_id)).map(c => <option key={c.context_id} value={c.context_id}>{c.name} ({c.status.toLowerCase()})</option>)}</Select></label>
      <Button type="submit" disabled={busy || !selection.length}>Save material details</Button>
    </form>
    <div className="flex flex-wrap gap-3">{active && !doc.archived && <Link to={`/?document=${doc.id}`} className="rounded-xl border border-border px-4 py-2 text-accent">Study in chat</Link>}<Button variant="secondary" disabled={busy || !!job} onClick={() => void action(() => updateMaterial(doc, { archived: !doc.archived }))}>{doc.archived ? 'Unarchive material' : 'Archive material'}</Button><Button variant="secondary" disabled={busy || !!job || doc.archived} onClick={() => void action(() => reindexMaterial(doc))}>Reindex material</Button><Button variant="secondary" disabled={busy} onClick={() => deleteDialog.current?.showModal()}>Delete material</Button></div>
    <form className="space-y-3 rounded-xl border border-border p-5" onSubmit={e => { e.preventDefault(); void action(async () => { const result = await tagMaterial(doc, conceptLabels.split(',').map(s => s.trim()).filter(Boolean)); setTagNotice(result.unresolved_labels.length ? `No canonical match for: ${result.unresolved_labels.join(', ')}. These labels were not attached.` : 'Canonical concept tags updated.'); }); }}><label className="block text-sm">Concept tags<Input className="mt-2" value={conceptLabels} onChange={e => setConceptLabels(e.target.value)} placeholder="Known concept names, separated by commas" /></label><p className="text-xs text-muted">Only concepts already recognized by Mentra can be attached. This does not change your learning estimates.</p><Button disabled={busy || !!job} variant="secondary" type="submit">Resolve concept tags</Button>{tagNotice && <p role="status" className="text-sm text-muted">{tagNotice}</p>}</form>
    <section><h2 className="font-medium">Source versions</h2>{(doc.archived || contexts.some(c => doc.context_ids.includes(c.context_id) && c.status === 'ARCHIVED')) && <Toggle className="mt-3" label="Allow viewing archived source material" checked={consent} onChange={e => setConsent(e.target.checked)} />}<ul className="mt-3 space-y-2">{versions.map((v, index) => <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border p-4 text-sm"><span>{v.filename} · {Math.ceil(v.size_bytes / 1024)} KiB {index === 0 ? '· Latest upload' : '· Earlier version'}</span><Button size="sm" variant="secondary" onClick={() => openVersion(v.id)}>Open source version</Button></li>)}</ul>{versions.length < doc.version_count && <Button className="mt-3" variant="secondary" disabled={loadingVersions} onClick={() => void loadVersions()}>{loadingVersions ? 'Loading versions…' : 'Load earlier versions'}</Button>}</section>
    {caps && !doc.archived && <MaterialUpload contexts={contexts} capabilities={caps} replacement={doc} onContextCreated={refresh} onAccepted={() => refresh()} />}
    {source && <SourceViewer source={source} filename={versions.find(v => v.id === source.version_id)?.filename} includeArchived={consent} onClose={() => setSource(undefined)} />}
    {createPortal(<dialog ref={deleteDialog} aria-label="Delete material confirmation" className="m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl border border-border bg-surface p-6 text-foreground backdrop:bg-black/40"><h2 className="font-medium">Delete {doc.title}?</h2><p className="mt-3 text-sm text-muted">This removes the material and its source versions. It stops appearing in chat immediately after the request is accepted; storage cleanup may take longer.</p><div className="mt-5 flex gap-3"><Button variant="secondary" onClick={() => deleteDialog.current?.close()}>Keep material</Button><Button disabled={busy} onClick={() => void action(async () => { await deleteMaterial(doc.id); deleteDialog.current?.close(); navigate('/library?deleted=1'); })}>Confirm deletion</Button></div></dialog>, document.body)}
  </section>;
}
