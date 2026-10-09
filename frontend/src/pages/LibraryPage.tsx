import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button, Select, Spinner } from '../components/ui';
import { MaterialUpload } from '../components/library/MaterialUpload';
import { getCapabilities, listContexts, listMaterials, pendingJob, materialError, transitionContext } from '../services/rag';
import type { LearningContext, MaterialList, RAGCapabilities } from '../types/rag';

export function LibraryPage() {
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get('offset')) || 0); const archive = params.get('archived') ?? 'available';
  const contextId = params.get('context') ?? '';
  function filterParams(values: Record<string, string>) { setParams({ archived: archive, ...(contextId ? { context: contextId } : {}), ...values }); }
  const [list, setList] = useState<MaterialList>(); const [contexts, setContexts] = useState<LearningContext[]>([]);
  const [capabilities, setCapabilities] = useState<RAGCapabilities>(); const [error, setError] = useState('');
  const [notice, setNotice] = useState(params.get('deleted') ? 'Material removed from your Library. Storage cleanup continues in the background.' : ''); const [reload, setReload] = useState(0);
  const refresh = useCallback(() => setReload(v => v + 1), []);
  useEffect(() => {
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout>; let running = false;
    async function load() {
      if (running || abort.signal.aborted) return;
      running = true;
      try {
        const [data, ctx, caps] = await Promise.all([listMaterials(offset, archive === 'all' ? undefined : archive === 'archived', abort.signal, contextId || undefined), listContexts(abort.signal), getCapabilities(abort.signal)]);
        if (abort.signal.aborted) return;
        setList(data); setContexts(ctx); setCapabilities(caps); setError('');
        if (data.items.some(pendingJob)) timer = setTimeout(() => { if (document.visibilityState === 'visible' && navigator.onLine) void load(); }, 3000);
      } catch (e) { if (!abort.signal.aborted) setError(materialError(e)); }
      finally { running = false; }
    }
    void load(); const onFocus = () => { if (document.visibilityState === 'visible') { clearTimeout(timer); void load(); } };
    window.addEventListener('focus', onFocus); window.addEventListener('online', onFocus); document.addEventListener('visibilitychange', onFocus);
    return () => { abort.abort(); clearTimeout(timer); window.removeEventListener('focus', onFocus); window.removeEventListener('online', onFocus); document.removeEventListener('visibilitychange', onFocus); };
  }, [offset, archive, contextId, reload]);
  async function changeContext(id: string, status: string) { try { await transitionContext(id, status); refresh(); } catch (e) { setError(materialError(e)); } }
  return <div className="h-full overflow-y-auto"><section className="page-container">
    <div><h1 className="page-title">Library</h1><p className="mt-2 text-sm text-muted">Your study material, ready to use in chat.</p></div>
    {notice && <p role="status" className="text-sm text-muted">{notice}</p>}
    {error && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">{error}<Button variant="secondary" onClick={refresh}>Try again</Button></div>}
    {!capabilities && !error && <Spinner />}
    {capabilities && <MaterialUpload contexts={contexts} capabilities={capabilities} onContextCreated={refresh} onAccepted={(_id, duplicate) => { setNotice(duplicate ? 'This material is already in your Library. No duplicate was created.' : 'Upload accepted. Your material is now processing.'); refresh(); }} />}
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="font-medium">Study materials {list ? `(${list.total})` : ''}</h2>
      <div className="flex flex-wrap gap-3">
        <label className="text-sm">Learning context<Select className="mt-1" value={contextId} onChange={e => filterParams({ context: e.target.value })}><option value="">All contexts</option>{contexts.map(c => <option key={c.context_id} value={c.context_id}>{c.name}</option>)}</Select></label>
        <label className="text-sm">Show<Select className="mt-1" value={archive} onChange={e => filterParams({ archived: e.target.value })}><option value="available">Available material</option><option value="archived">Archived material</option><option value="all">All material</option></Select></label>
      </div>
    </div>
    {list?.items.length === 0 && <p className="rounded-xl border border-border p-5 text-sm text-muted">{archive === 'archived' ? 'No archived material.' : 'Add material above to start studying from your sources.'}</p>}
    <ul className="space-y-3">{list?.items.map(doc => { const job = pendingJob(doc); return <li key={doc.id} className="rounded-xl border border-border bg-surface p-4"><div className="flex flex-wrap justify-between gap-3"><Link className="font-medium text-foreground underline-offset-4 hover:underline" to={`/library/${doc.id}`}>{doc.title}</Link><span className="text-xs text-muted">{job ? job.stage : doc.active_generation_id ? 'Ready' : doc.jobs[0]?.state.toLowerCase() ?? 'Pending'}{doc.archived ? ' · Archived' : ''}</span></div><p className="mt-2 text-xs text-subtle">{doc.context_ids.map(id => contexts.find(c => c.context_id === id)?.name ?? 'Context').join(', ')} · {doc.filename}</p>{doc.jobs[0]?.error && <p className="mt-2 text-sm text-danger">{doc.jobs[0].error}</p>}<div className="mt-3 flex gap-4 text-sm"><Link to={`/library/${doc.id}`} className="text-accent">View material</Link>{doc.active_generation_id && !doc.archived && <Link to={`/?document=${doc.id}`} className="text-accent">Study in chat</Link>}</div></li>; })}</ul>
    {list && list.total > list.limit && <div className="flex items-center justify-between"><Button variant="secondary" disabled={offset === 0} onClick={() => filterParams({ offset: String(Math.max(0, offset - list.limit)) })}>Previous</Button><span className="text-sm text-muted">{offset + 1}–{Math.min(offset + list.limit, list.total)} of {list.total}</span><Button variant="secondary" disabled={offset + list.limit >= list.total} onClick={() => filterParams({ offset: String(offset + list.limit) })}>Next</Button></div>}
    {contexts.length > 0 && <section className="border-t border-border pt-5"><h2 className="font-medium">Learning contexts</h2><p className="mt-1 text-sm text-muted">Current and related contexts guide automatic retrieval. Dormant contexts can be selected deliberately. Archived contexts require explicit inclusion.</p><ul className="mt-3 space-y-2">{contexts.map(c => <li key={c.context_id} className="flex flex-wrap items-center justify-between gap-2 text-sm"><span>{c.name}</span><label>State for {c.name}<Select className="ml-2 inline-block w-auto" value={c.status} onChange={e => void changeContext(c.context_id, e.target.value)}><option value="ACTIVE">Current</option><option value="RELATED">Related</option><option value="DORMANT">Dormant</option><option value="ARCHIVED">Archived</option></Select></label></li>)}</ul></section>}
  </section></div>;
}
