import { useEffect, useState } from 'react';
import { BookOpen, Search, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button, Input, Pagination } from '../ui';
import { Skeleton } from '../ui/Skeleton';
import { WorkspaceEmpty } from '../workspace/WorkspaceHeader';
import { learningProgress } from '../../services/learning';
import type { LearningProgressPage } from '../../types/learning';
import { progressStatus } from './progressLabels';

interface Props { context: string; reload: number; onTotal: (total: number) => void }
const percent = (value: number | null) => value === null ? 'Not yet known' : `${Math.round(value * 100)}%`;

export function UnderstandingTable({context, reload, onTotal}: Props) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<LearningProgressPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (search.trim() === query) return;
    const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 250);
    return () => clearTimeout(timer);
  }, [search, query]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setData(null);
    void learningProgress(controller.signal, query, (page - 1) * 10, context || undefined).then(value => {
      if (controller.signal.aborted) return;
      setData(value); onTotal(value.total_concepts);
    }).catch(() => { if (!controller.signal.aborted) setError('Couldn’t load your understanding. Please try again.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [context, query, page, reload, retry, onTotal]);
  const current = data ? Math.floor(data.offset / data.limit) + 1 : page;
  return <section aria-labelledby="understanding-title" className="workspace-panel space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><h2 id="understanding-title" className="flex items-center gap-2 text-lg font-medium text-heading"><BookOpen size={19} aria-hidden="true" />Your understanding</h2>
        <p className="mt-1 max-w-lg text-sm text-muted">Topics in your learning contexts, with estimates based on your practice and answers. “Getting started” means Mentra needs more practice to form a reliable picture.</p></div>
      <div className="relative w-full sm:w-64"><Search size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-3 text-subtle" />
        <Input type="search" aria-label="Search your understanding" placeholder="Search topics…" maxLength={200} className="pl-9 pr-9" value={search} onChange={event => setSearch(event.target.value)} />
        {search && <button type="button" aria-label="Clear topic search" className="absolute right-2 top-2 rounded-lg p-1 text-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setSearch('')}><X size={16} aria-hidden="true" /></button>}
      </div>
    </div>
    {loading && <div aria-label="Loading understanding"><Skeleton variant="table" /></div>}
    {error && <p role="alert" className="text-sm text-danger">{error} <Button variant="ghost" size="sm" onClick={() => setRetry(value => value + 1)}>Retry</Button></p>}
    {data && !data.items.length && <WorkspaceEmpty icon={BookOpen} title={query ? 'No matching topics' : 'Every step builds understanding'}
      description={query ? 'Try another topic name or clear your search.' : 'Practice or complete an assessment to start building your learning profile.'}
      action={query ? <Button variant="ghost" size="sm" onClick={() => setSearch('')}>Clear search</Button> : <Link className="text-sm text-accent hover:underline" to="/assessments?tab=create">Create a practice assessment</Link>} />}
    {data && !!data.items.length && <>
      <div className="overflow-x-auto"><table aria-label="Your understanding" className="w-full text-left text-sm">
        <thead className="bg-background text-muted"><tr>{['Topic', 'Learning status', 'Understanding estimate', 'Estimate reliability', 'Recall confidence'].map(label => <th key={label} scope="col" className="whitespace-nowrap border-b border-border px-3 py-2 font-medium">{label}</th>)}</tr></thead>
        <tbody>{data.items.map(item => <tr key={item.concept_id}>
          <th scope="row" className="border-b border-border px-3 py-3 font-medium">{item.name}</th>
          <td className="border-b border-border px-3 py-3"><span className="whitespace-nowrap rounded-full bg-active px-2.5 py-1 text-xs text-heading">{progressStatus(item.knowledge_status)}</span></td>
          {[item.mastery, item.estimate_confidence, item.retention_confidence].map((value, index) => <td key={index} className="whitespace-nowrap border-b border-border px-3 py-3 text-muted">{percent(value)}</td>)}
        </tr>)}</tbody></table></div>
      <div className="flex flex-wrap items-center justify-between gap-3"><p role="status" className="text-xs text-muted">Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total} topics</p>
        <Pagination page={current} pages={Math.ceil(data.total / data.limit)} onChange={setPage} label="Understanding pages" /></div>
    </>}
    <details className="text-xs text-muted"><summary className="cursor-pointer text-heading">What do these estimates mean?</summary>
      <div className="mt-2 space-y-2"><p>Understanding estimates reflect how you’ve answered questions. They are learning indicators, not exam grades.</p>
        <p>Estimate reliability describes how much support there is for that estimate. Recall confidence considers how recently you practised. An unknown value means Mentra doesn’t have enough information yet.</p></div>
    </details>
  </section>;
}
