import { PageShell, PageSkeleton, PageSection } from '../components/workspace/PageShell';
import { invalidatePageCache } from '../services/pageCache';
import { practiceLink } from '../services/practiceIntent';
import { BookOpen, FileText, FolderOpen, Plus, MessageSquare, ClipboardCheck, ArrowUpRight } from 'lucide-react';
import { WorkspaceHeader, WorkspaceEmpty } from '../components/workspace/WorkspaceHeader';
import { usePendingWork, usePageRefresh, refreshPage } from '../hooks/usePageRefresh';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Input, Select, Pagination, buttonStyles } from '../components/ui';
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
  return <PageShell className="library-page">
    <WorkspaceHeader title="Library" description="Keep your sources together. Bring them into a conversation whenever you’re ready to study." icon={BookOpen} actions={<Button onClick={() => navigate('/library/new')}><Plus size={16} aria-hidden="true" />Add material</Button>} />
    {notice && <p role="status" className="text-sm text-muted">{notice}</p>}
    {error && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">{error}<Button variant="secondary" onClick={() => refreshPage(refresh)}>Try again</Button></div>}
    <PageSection title="Study materials" description="A source for every part of your learning." className="library-filters" actions={visible && <span className="library-count">{visible.total} {visible.total === 1 ? 'material' : 'materials'}</span>}>
      <div className="library-filter-grid">
      <form className="library-query" role="search" onSubmit={event => { event.preventDefault(); filterParams({ query: search.trim(), offset: '0' }); }}><label htmlFor="library-query" className="text-sm">Find a source</label><div className="flex min-w-0 gap-2"><Input id="library-query" type="search" aria-label="Search Library" placeholder="Search titles or filenames…" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} /><Button type="submit" variant="secondary">Search</Button>{query && <Button variant="ghost" onClick={() => { setSearch(''); filterParams({ query: '', offset: '0' }); }}>Clear</Button>}</div></form>
      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
        <label className="text-sm">Learning context<Select className="mt-1" value={contextId} onChange={e => filterParams({ context: e.target.value })}><option value="">All contexts</option>{contexts.map(c => <option key={c.context_id} value={c.context_id}>{c.name}</option>)}</Select></label>
        <label className="text-sm">Show<Select className="mt-1" value={archive} onChange={e => filterParams({ archived: e.target.value })}><option value="available">Available material</option><option value="archived">Archived material</option><option value="all">All material</option></Select></label>
      </div>
      </div>
    </PageSection>
    {!visible && !error && <PageSkeleton />}
    {visible?.items.length === 0 && <WorkspaceEmpty title={query ? 'No matching materials' : archive === 'archived' ? 'No archived material' : 'Your next source starts here'} description="Add notes, books, documents or images, then study with them in chat." icon={FolderOpen} action={archive !== 'archived' && <Button variant="secondary" onClick={() => navigate('/library/new')}>Add your first material</Button>} />}
    <ul className="workspace-grid library-materials">{visible?.items.map(doc => { const job = pendingJob(doc); return <li key={doc.id} className="workspace-item library-material"><div className="flex items-center justify-between gap-3"><span className="library-file-icon"><FileText size={21} strokeWidth={1.5} aria-hidden="true" /></span><span className={`library-material-status ${job ? 'is-preparing' : doc.active_generation_id ? 'is-ready' : ''}`}>{job ? 'Preparing' : doc.active_generation_id ? 'Ready to study' : doc.jobs[0]?.error ? 'Needs attention' : 'Pending'}{doc.archived ? ' · Archived' : ''}</span></div><div className="min-w-0"><Link className="library-material-title" to={`/library/${doc.id}`}>{doc.title}</Link><p className="mt-2 break-all text-xs text-muted">{doc.filename}</p></div><div className="library-context-tags">{doc.context_ids.map(id => <span key={id}>{contexts.find(context => context.context_id === id)?.name ?? 'Context'}</span>)}</div>{doc.jobs[0]?.error && <p className="text-sm text-danger">This material could not be processed.</p>}<div className="library-material-actions"><Link to={`/library/${doc.id}`} className={buttonStyles({variant: 'ghost', size: 'sm', className: '-ml-2' })}>View material<ArrowUpRight size={14} aria-hidden="true" /></Link><div className="flex flex-wrap gap-1">{doc.active_generation_id && !doc.archived && <Link to={`/?document=${doc.id}`} className={buttonStyles({variant: 'secondary', size: 'sm'})}><MessageSquare size={14} aria-hidden="true" />Study in chat</Link>}{doc.active_generation_id && !doc.archived && <Link className={buttonStyles({variant: 'ghost', size: 'sm'})} to={practiceLink({ document_ids: [doc.id], context_id: contexts.find(item => doc.context_ids.includes(item.context_id) && item.status !== 'ARCHIVED')?.context_id, topic: doc.title })}><ClipboardCheck size={14} aria-hidden="true" />Quiz this material</Link>}</div></div></li>; })}</ul>
    {visible && visible.total > visible.limit && <div className="flex flex-wrap items-center justify-between gap-3"><span className="text-xs text-muted">{offset + 1}–{Math.min(offset + visible.limit, visible.total)} of {visible.total} materials</span><Pagination label="Library pages" page={Math.floor(offset / visible.limit) + 1} pages={Math.ceil(visible.total / visible.limit)} onChange={page => filterParams({ offset: String((page - 1) * visible.limit) })} /></div>}
    {contexts.length > 0 && <PageSection title="Learning contexts" description="Keep related sources together. Set what you’re focusing on now." className="library-context-manager"><ul className="library-context-list">{contexts.map(c => <li key={c.context_id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"><span className="min-w-0 flex-1 break-words">{c.name}</span><label><span className="sr-only">State for {c.name}</span><Select className="ml-2 inline-block w-auto" value={c.status} onChange={e => void changeContext(c.context_id, e.target.value)}><option value="ACTIVE">Current</option><option value="RELATED">Related</option><option value="DORMANT">Dormant</option><option value="ARCHIVED">Archived</option></Select></label></li>)}</ul></PageSection>}
  </PageShell>;
}
