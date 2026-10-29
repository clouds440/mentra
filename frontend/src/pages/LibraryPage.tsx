import { PageShell, PageSkeleton, PageToolbar } from '../components/workspace/PageShell';
import { invalidatePageCache } from '../services/pageCache';
import { practiceLink } from '../services/practiceIntent';
import { BookOpen, FileText, FolderOpen, Plus, MessageSquare, ClipboardCheck, ArrowUpRight } from 'lucide-react';
import { WorkspaceHeader, WorkspaceEmpty } from '../components/workspace/WorkspaceHeader';
import { usePendingWork, usePageRefresh, refreshPage } from '../hooks/usePageRefresh';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Input, Select, buttonStyles } from '../components/ui';
import { libraryPage, pendingJob, materialError, transitionContext } from '../services/rag';
import type { LearningContext, MaterialList } from '../types/rag';

export function LibraryPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const requestedOffset = Number(params.get('offset'));
  const offset = Number.isSafeInteger(requestedOffset) && requestedOffset >= 0 ? requestedOffset : 0;
  const requestedArchive = params.get('archived');
  const archive = requestedArchive === 'all' || requestedArchive === 'archived' ? requestedArchive : 'available';
  const contextId = params.get('context') ?? '';
  const query = params.get('query') ?? '';
  const [search, setSearch] = useState(query);
  useEffect(() => setSearch(query), [query]);
  function filterParams(values: Record<string, string>) { setParams({ archived: archive, ...(contextId ? { context: contextId } : {}), ...(query ? { query } : {}), ...values }); }
  const [list, setList] = useState<MaterialList>(); const [loadedQuery, setLoadedQuery] = useState('');
  const queryKey = JSON.stringify([offset, archive, contextId, query]); const visible = loadedQuery === queryKey ? list : undefined; const [contexts, setContexts] = useState<LearningContext[]>([]);
  const [error, setError] = useState('');
  const notice = params.get('deleted') ? 'Material removed from your Library. Storage cleanup continues in the background.'
    : params.get('uploaded') === 'duplicate' ? 'This material is already in your Library. No duplicate was created.'
    : params.get('uploaded') === 'accepted' ? 'Upload accepted. Your material is now processing.' : '';
  const [reload, setReload] = useState(0);
  const processing = useRef(false);
  const request = useRef<AbortController>();
  const refresh = useCallback(() => setReload(v => v + 1), []);
  usePageRefresh(() => { if (!request.current) refresh(); }, true, ['documents', 'learning-contexts']);
  usePendingWork(() => { if (!request.current) refresh(); }, !!list?.items.some(pendingJob));
  useEffect(() => {
    const abort = new AbortController(); request.current = abort; setError('');
    async function load() {
      try {
        const data = await libraryPage(offset, archive === 'all' ? undefined : archive === 'archived', abort.signal, contextId || undefined, query);
        if (abort.signal.aborted) return;
        const isProcessing = data.items.some(pendingJob);
        if (processing.current && !isProcessing) invalidatePageCache(['documents', 'learning'], true);
        processing.current = isProcessing;
        setList(data); setLoadedQuery(queryKey); setContexts(data.contexts); setError('');

      } catch (e) { if (!abort.signal.aborted) setError(materialError(e)); }
      finally { if (request.current === abort) request.current = undefined; }
    }
    void load(); return () => { abort.abort(); if (request.current === abort) request.current = undefined; };
  }, [offset, archive, contextId, query, reload]);
  async function changeContext(id: string, status: string) { try { await transitionContext(id, status); refresh(); } catch (e) { setError(materialError(e)); } }
  return <PageShell>
    <WorkspaceHeader title="Library" description="Keep your sources together. Bring them into a conversation whenever you’re ready to study." icon={BookOpen} actions={<Button onClick={() => navigate('/library/new')}><Plus size={16} aria-hidden="true" />Add material</Button>} />
    {notice && <p role="status" className="text-sm text-muted">{notice}</p>}
    {error && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">{error}<Button variant="secondary" onClick={() => refreshPage(refresh)}>Try again</Button></div>}
    <form className="library-search" role="search" onSubmit={event => { event.preventDefault(); filterParams({ query: search.trim(), offset: '0' }); }}><Input type="search" aria-label="Search Library" placeholder="Search titles or filenames…" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} /><Button type="submit" variant="secondary">Search</Button>{query && <Button variant="ghost" onClick={() => { setSearch(''); filterParams({ query: '', offset: '0' }); }}>Clear</Button>}</form>
    <PageToolbar>
      <h2 className="font-medium">Study materials {visible ? `(${visible.total})` : ''}</h2>
      <div className="grid w-full gap-3 sm:max-w-xl sm:grid-cols-2">
        <label className="text-sm">Learning context<Select className="mt-1" value={contextId} onChange={e => filterParams({ context: e.target.value })}><option value="">All contexts</option>{contexts.map(c => <option key={c.context_id} value={c.context_id}>{c.name}</option>)}</Select></label>
        <label className="text-sm">Show<Select className="mt-1" value={archive} onChange={e => filterParams({ archived: e.target.value })}><option value="available">Available material</option><option value="archived">Archived material</option><option value="all">All material</option></Select></label>
      </div>
    </PageToolbar>
    {!visible && !error && <PageSkeleton />}
    {visible?.items.length === 0 && <WorkspaceEmpty title={query ? 'No matching materials' : archive === 'archived' ? 'No archived material' : 'Your next source starts here'} description="Add notes, books, documents or images, then study with them in chat." icon={FolderOpen} action={archive !== 'archived' && <Button variant="secondary" onClick={() => navigate('/library/new')}>Add your first material</Button>} />}
    <ul className="workspace-grid">{visible?.items.map(doc => { const job = pendingJob(doc); return <li key={doc.id} className="workspace-item flex flex-col gap-3"><div className="flex flex-wrap items-start gap-2"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-active text-accent"><FileText size={19} aria-hidden="true" /></span><Link className="min-w-0 flex-1 break-words font-medium text-heading underline-offset-4 hover:underline" to={`/library/${doc.id}`}>{doc.title}</Link><span className="workspace-status">{job ? 'Preparing' : doc.active_generation_id ? 'Ready' : doc.jobs[0]?.error ? 'Needs attention' : 'Pending'}{doc.archived ? ' · Archived' : ''}</span></div><p className="mt-2 break-words text-xs text-subtle">{doc.context_ids.map(id => contexts.find(c => c.context_id === id)?.name ?? 'Context').join(', ')} · {doc.filename}</p>{doc.jobs[0]?.error && <p className="mt-2 text-sm text-danger">This material could not be processed.</p>}<div className="mt-auto flex flex-wrap gap-2 border-t border-border pt-3 text-sm"><Link to={`/library/${doc.id}`} className={buttonStyles({variant: 'secondary', size: 'sm'})}><ArrowUpRight size={14} aria-hidden="true" />View material</Link>{doc.active_generation_id && !doc.archived && <Link to={`/?document=${doc.id}`} className={buttonStyles({variant: 'secondary', size: 'sm'})}><MessageSquare size={14} aria-hidden="true" />Study in chat</Link>}{doc.active_generation_id && !doc.archived && <Link className={buttonStyles({variant: 'secondary', size: 'sm'})} to={practiceLink({ document_ids: [doc.id], context_id: contexts.find(item => doc.context_ids.includes(item.context_id) && item.status !== 'ARCHIVED')?.context_id, topic: doc.title })}><ClipboardCheck size={14} aria-hidden="true" />Quiz this material</Link>}</div></li>; })}</ul>
    {visible && visible.total > visible.limit && <div className="flex items-center justify-between"><Button variant="secondary" disabled={offset === 0} onClick={() => filterParams({ offset: String(Math.max(0, offset - visible.limit)) })}>Previous</Button><span className="text-sm text-muted">{offset + 1}–{Math.min(offset + visible.limit, visible.total)} of {visible.total}</span><Button variant="secondary" disabled={offset + visible.limit >= visible.total} onClick={() => filterParams({ offset: String(offset + visible.limit) })}>Next</Button></div>}
    {contexts.length > 0 && <section className="workspace-panel"><h2 className="flex items-center gap-2 font-medium text-heading"><FolderOpen size={18} aria-hidden="true" />Learning contexts</h2><p className="mt-2 text-sm leading-6 text-muted">Organize what you’re studying. Current and related contexts help Mentra choose relevant material.</p><ul className="mt-3 space-y-2">{contexts.map(c => <li key={c.context_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-background p-3 text-sm"><span>{c.name}</span><label><span className="sr-only">State for {c.name}</span><Select className="ml-2 inline-block w-auto" value={c.status} onChange={e => void changeContext(c.context_id, e.target.value)}><option value="ACTIVE">Current</option><option value="RELATED">Related</option><option value="DORMANT">Dormant</option><option value="ARCHIVED">Archived</option></Select></label></li>)}</ul></section>}
  </PageShell>;
}
