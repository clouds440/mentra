import { BookOpen, FileText, FolderOpen, Plus } from 'lucide-react';
import { WorkspaceHeader, WorkspaceEmpty } from '../components/workspace/WorkspaceHeader';
import { usePageRefresh, refreshPage } from '../hooks/usePageRefresh';
import { Skeleton } from '../components/ui/Skeleton';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Select } from '../components/ui';
import { listContexts, listMaterials, pendingJob, materialError, transitionContext } from '../services/rag';
import type { LearningContext, MaterialList } from '../types/rag';

export function LibraryPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get('offset')) || 0); const archive = params.get('archived') ?? 'available';
  const contextId = params.get('context') ?? '';
  function filterParams(values: Record<string, string>) { setParams({ archived: archive, ...(contextId ? { context: contextId } : {}), ...values }); }
  const [list, setList] = useState<MaterialList>(); const [contexts, setContexts] = useState<LearningContext[]>([]);
  const [error, setError] = useState('');
  const notice = params.get('deleted') ? 'Material removed from your Library. Storage cleanup continues in the background.'
    : params.get('uploaded') === 'duplicate' ? 'This material is already in your Library. No duplicate was created.'
    : params.get('uploaded') === 'accepted' ? 'Upload accepted. Your material is now processing.' : '';
  const [reload, setReload] = useState(0);
  const refresh = useCallback(() => setReload(v => v + 1), []);
  usePageRefresh(refresh, true);
  useEffect(() => {
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout>; let running = false;
    async function load() {
      if (running || abort.signal.aborted) return;
      running = true;
      try {
        const [data, ctx] = await Promise.all([listMaterials(offset, archive === 'all' ? undefined : archive === 'archived', abort.signal, contextId || undefined), listContexts(abort.signal)]);
        if (abort.signal.aborted) return;
        setList(data); setContexts(ctx); setError('');
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
    <WorkspaceHeader title="Library" description="Keep your sources together. Bring them into a conversation whenever you’re ready to study." icon={BookOpen} actions={<Button onClick={() => navigate('/library/new')}><Plus size={16} aria-hidden="true" />Add material</Button>} />
    {notice && <p role="status" className="text-sm text-muted">{notice}</p>}
    {error && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">{error}<Button variant="secondary" onClick={() => refreshPage(refresh)}>Try again</Button></div>}
    {!list && !error && <Skeleton variant="card" />}
    <div className="workspace-toolbar">
      <h2 className="font-medium">Study materials {list ? `(${list.total})` : ''}</h2>
      <div className="flex flex-wrap gap-3">
        <label className="text-sm">Learning context<Select className="mt-1" value={contextId} onChange={e => filterParams({ context: e.target.value })}><option value="">All contexts</option>{contexts.map(c => <option key={c.context_id} value={c.context_id}>{c.name}</option>)}</Select></label>
        <label className="text-sm">Show<Select className="mt-1" value={archive} onChange={e => filterParams({ archived: e.target.value })}><option value="available">Available material</option><option value="archived">Archived material</option><option value="all">All material</option></Select></label>
      </div>
    </div>
    {list?.items.length === 0 && <WorkspaceEmpty title={archive === 'archived' ? 'No archived material' : 'Your next source starts here'} description="Add notes, books, documents or images, then study with them in chat." icon={FolderOpen} action={archive !== 'archived' && <Button variant="secondary" onClick={() => navigate('/library/new')}>Add your first material</Button>} />}
    <ul className="workspace-grid">{list?.items.map(doc => { const job = pendingJob(doc); return <li key={doc.id} className="workspace-item flex flex-col gap-3"><div className="flex items-start gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-active text-accent"><FileText size={19} aria-hidden="true" /></span><Link className="min-w-0 flex-1 break-words font-medium text-heading underline-offset-4 hover:underline" to={`/library/${doc.id}`}>{doc.title}</Link><span className="workspace-status shrink-0">{job ? 'Preparing' : doc.active_generation_id ? 'Ready' : doc.jobs[0]?.error ? 'Needs attention' : 'Pending'}{doc.archived ? ' · Archived' : ''}</span></div><p className="mt-2 break-words text-xs text-subtle">{doc.context_ids.map(id => contexts.find(c => c.context_id === id)?.name ?? 'Context').join(', ')} · {doc.filename}</p>{doc.jobs[0]?.error && <p className="mt-2 text-sm text-danger">This material could not be processed.</p>}<div className="mt-auto flex gap-4 border-t border-border pt-3 text-sm"><Link to={`/library/${doc.id}`} className="text-accent">View material</Link>{doc.active_generation_id && !doc.archived && <Link to={`/?document=${doc.id}`} className="text-accent">Study in chat</Link>}</div></li>; })}</ul>
    {list && list.total > list.limit && <div className="flex items-center justify-between"><Button variant="secondary" disabled={offset === 0} onClick={() => filterParams({ offset: String(Math.max(0, offset - list.limit)) })}>Previous</Button><span className="text-sm text-muted">{offset + 1}–{Math.min(offset + list.limit, list.total)} of {list.total}</span><Button variant="secondary" disabled={offset + list.limit >= list.total} onClick={() => filterParams({ offset: String(offset + list.limit) })}>Next</Button></div>}
    {contexts.length > 0 && <section className="workspace-panel"><h2 className="flex items-center gap-2 font-medium text-heading"><FolderOpen size={18} aria-hidden="true" />Learning contexts</h2><p className="mt-2 text-sm leading-6 text-muted">Organize what you’re studying. Current and related contexts help Mentra choose relevant material.</p><ul className="mt-3 space-y-2">{contexts.map(c => <li key={c.context_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-background p-3 text-sm"><span>{c.name}</span><label><span className="sr-only">State for {c.name}</span><Select className="ml-2 inline-block w-auto" value={c.status} onChange={e => void changeContext(c.context_id, e.target.value)}><option value="ACTIVE">Current</option><option value="RELATED">Related</option><option value="DORMANT">Dormant</option><option value="ARCHIVED">Archived</option></Select></label></li>)}</ul></section>}
  </section></div>;
}
