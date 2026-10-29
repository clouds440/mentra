import { PageSection } from '../workspace/PageShell';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, ChevronRight, X } from 'lucide-react';
import { Button, Dialog, Input, Pagination } from '../ui';
import { buttonStyles } from '../ui/Button';
import { Skeleton } from '../ui/Skeleton';
import { applyTopicGrouping, learningTopics, moveLearningSubskill, organizeLearningTopics, renameLearningTopic, topicSubskills, type TopicGroupingPreview } from '../../services/learning';
import { practiceLink } from '../../services/practiceIntent';
import type { LearningTopicsPage, TopicSkillsPage } from '../../types/learning';
import { progressStatus } from './progressLabels';
import { ProgressEvidence } from './ProgressEvidence';
import { MoveSubskill, type SkillMove } from './MoveSubskill';
import { invalidatePageCache } from '../../services/pageCache';

export function TopicProgress({ context, reload, onTotal }: { context: string; reload: number; onTotal: (value: number) => void }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [data, setData] = useState<LearningTopicsPage>();
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string>();
  const [selectedQuery, setSelectedQuery] = useState('');
  const [organizing, setOrganizing] = useState(false);
  const [preview, setPreview] = useState<TopicGroupingPreview>();
  const [lastGrouping, setLastGrouping] = useState<number>();
  const operation = useRef<AbortController>();
  useEffect(() => () => operation.current?.abort(), []);
  useEffect(() => { if (search.trim() === query) return; const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 250); return () => clearTimeout(timer); }, [search, query]);
  useEffect(() => {
    const controller = new AbortController(); setData(undefined); setError('');
    void learningTopics(controller.signal, context, query, (page - 1) * 10).then(value => {
      if (!controller.signal.aborted) { setData(value); onTotal(value.total); }
    }).catch(() => { if (!controller.signal.aborted) setError('Couldn’t load your topics. Please try again.'); });
    return () => controller.abort();
  }, [context, query, page, reload, version, onTotal]);
  async function organize() {
    if (!context || organizing) return;
    const controller = new AbortController(); operation.current = controller; setOrganizing(true); setError('');
    try {
      // Small committed batches retain progress after cancellation or a failure.
      const value = await organizeLearningTopics(context, controller.signal);
      if (!controller.signal.aborted) { setPreview(value); if (value.unresolved) setError('Some skills could not be placed reliably. They remain available under Not grouped yet.'); }
    } catch { if (!controller.signal.aborted) setError('Couldn’t organize these skills. Your learning history is unchanged; please retry.'); }
    finally { if (!controller.signal.aborted) { setOrganizing(false); operation.current = undefined; } }
  }
  async function apply(id: number, undo = false) {
    if (organizing) return;
    const controller = new AbortController(); operation.current = controller; setOrganizing(true); setError('');
    try {
      await applyTopicGrouping(id, controller.signal, undo);
      if (!controller.signal.aborted) { setPreview(undefined); setLastGrouping(undo ? undefined : id); setVersion(value => value + 1); invalidatePageCache(['learning'], true); }
    } catch { if (!controller.signal.aborted) setError('Couldn’t update this grouping. It may have changed elsewhere; refresh and retry.'); }
    finally { if (!controller.signal.aborted) { setOrganizing(false); operation.current = undefined; } }
  }
  return <PageSection aria-labelledby="understanding-title" className="workspace-panel space-y-4">
    {selected && <TopicDetail key={`${context}:${selected}`} id={selected} context={context} initialQuery={selectedQuery} onClose={() => setSelected(undefined)} />}
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 id="understanding-title" className="flex items-center gap-2 text-lg font-medium text-heading"><BookOpen size={19} aria-hidden="true" />Your understanding</h2><p className="mt-1 max-w-xl text-sm text-muted">Explore broader topics, then open the specific skills inside. Checked skills describe your practice so far, not coverage of a whole syllabus.</p></div>
      <Input type="search" className="w-full sm:max-w-xs" aria-label="Search topics and subskills" placeholder="Search topics or subskills…" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} />
    </div>
    {error && <p role="alert" className="text-sm text-danger">{error} <Button variant="ghost" size="sm" onClick={() => setVersion(value => value + 1)}>Retry</Button></p>}
    {preview?.proposal_id && <section aria-label="Grouping preview" className="space-y-3 rounded-control border border-border p-3"><h3 className="text-sm font-medium text-heading">Review the proposed grouping</h3><p className="text-xs text-muted">Your skills, answers and scores stay intact. Only their placement changes.</p><ul className="space-y-1 text-sm text-heading">{preview.placements?.map((item, index) => <li key={index}>{item.topic_name} · {item.subskill_name}</li>)}</ul><div className="flex flex-wrap gap-2"><Button size="sm" disabled={organizing} loading={organizing} onClick={() => void apply(preview.proposal_id!)}>Apply grouping</Button><Button size="sm" variant="ghost" disabled={organizing} onClick={() => setPreview(undefined)}>Dismiss</Button></div></section>}
    {lastGrouping && <p role="status" className="text-xs text-muted">Grouping applied. <Button size="sm" variant="ghost" disabled={organizing} onClick={() => void apply(lastGrouping, true)}>Undo grouping</Button></p>}
    {!data && !error && <Skeleton variant="list" rows={3} />}
    {data && <>
      {!!data.ungrouped_count && <div className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-border p-3"><div><button className="text-left text-sm font-medium text-heading underline decoration-border underline-offset-4 focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setSelected('ungrouped')}>{data.ungrouped_count} skills not grouped yet</button><p className="mt-1 text-xs text-muted">Their evidence and results are preserved.{!context && ' Choose a learning area to organize them.'}</p></div>{context && <Button variant="secondary" size="sm" loading={organizing} disabled={organizing} onClick={() => void organize()}>Organize next skills</Button>}</div>}
      {!data.items.length && <p className="text-sm text-muted">{query ? 'No matching topics. Try another term.' : 'Topics appear as you practise. Existing skills can be organized into broader topics.'}</p>}
      <ul className="divide-y divide-border">{data.items.map(topic => <li key={topic.id} className="py-4"><button className="flex w-full items-start justify-between gap-3 rounded-control text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" onClick={() => { setSelectedQuery(topic.matching_skills?.length ? query : ''); setSelected(topic.id); }} aria-label={`Explore ${topic.name}`}><span><span className="font-medium text-heading">{topic.name}</span><span className="mt-1 block text-sm text-muted">{topic.scope}</span><span className="mt-2 block text-xs text-muted">{topic.checked_count} of {topic.subskill_count} tracked subskills checked</span>{!!topic.matching_skills?.length && <span className="mt-1 block text-xs text-accent">Matches: {topic.matching_skills.join(', ')}</span>}</span><ChevronRight size={18} className="mt-1 shrink-0 text-muted" aria-hidden="true" /></button></li>)}</ul>
      {data.total > 10 && <Pagination page={Math.floor(data.offset / data.limit) + 1} pages={Math.ceil(data.total / data.limit)} onChange={setPage} label="Learning topics" />}
    </>}
  </PageSection>;
}

function TopicDetail({ id, context, initialQuery, onClose }: { id: string; context: string; initialQuery: string; onClose: () => void }) {
  const [search, setSearch] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<TopicSkillsPage>();
  const [error, setError] = useState('');
  const [evidence, setEvidence] = useState<string>();
  const [retry, setRetry] = useState(0);
  const [lastMove, setLastMove] = useState<SkillMove>();
  const [saving, setSaving] = useState(false);
  const mutation = useRef<AbortController>();
  useEffect(() => () => mutation.current?.abort(), []);
  async function save(change: (signal: AbortSignal) => Promise<unknown>) {
    if (saving) return;
    const controller = new AbortController(); mutation.current = controller; setSaving(true); setError('');
    try { await change(controller.signal); if (!controller.signal.aborted) { setLastMove(undefined); setRetry(value => value + 1); invalidatePageCache(['learning'], true); } }
    catch { if (!controller.signal.aborted) setError('Couldn’t update this topic. Refresh and retry; its placement may have changed.'); }
    finally { if (!controller.signal.aborted) setSaving(false); }
  }
  useEffect(() => { if (search.trim() === query) return; const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 250); return () => clearTimeout(timer); }, [search, query]);
  useEffect(() => {
    const controller = new AbortController(); setData(undefined); setError('');
    void topicSubskills(id, controller.signal, context, query, (page - 1) * 10).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(() => { if (!controller.signal.aborted) setError('Couldn’t load these subskills. Please retry.'); });
    return () => controller.abort();
  }, [id, context, query, page, retry]);
  return <Dialog open onDismiss={onClose} aria-label="Topic subskills" className="flex max-h-[88dvh] max-w-2xl flex-col overflow-hidden p-0">
    {evidence && <ProgressEvidence concept={evidence} context={context} onClose={() => setEvidence(undefined)} />}
    <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border p-5"><div><h2 className="text-lg font-medium text-heading">{data?.topic.name ?? 'Subskills'}</h2><p className="mt-1 text-sm text-muted">{data?.topic.scope}</p></div><Button variant="ghost" size="sm" aria-label="Close subskills" onClick={onClose}><X size={18} /></Button></header>
    <div className="min-h-0 space-y-4 overflow-y-auto overscroll-contain p-5" data-skill-scroll>
      <Input type="search" aria-label="Search subskills" placeholder="Search inside this topic…" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} />
      {data && id !== 'ungrouped' && <details className="text-xs text-muted"><summary className="ui-disclosure cursor-pointer">Rename topic</summary><form className="mt-2 flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); const name = String(new FormData(event.currentTarget).get('topic_name') ?? '').trim(); if (name) void save(signal => renameLearningTopic(id, name, data.topic.revision, signal)); }}><Input name="topic_name" aria-label="Topic name" defaultValue={data.topic.name} maxLength={200} required disabled={saving} /><Button size="sm" type="submit" disabled={saving}>Save name</Button></form></details>}
      {lastMove && <p role="status" className="text-xs text-muted">Skill moved. <Button size="sm" variant="ghost" disabled={saving} onClick={() => void save(signal => moveLearningSubskill(id, lastMove.skill, lastMove.target, 1, lastMove.operation, signal, true))}>Undo move</Button></p>}
      {error && <p role="alert" className="text-sm text-danger">{error} <Button variant="ghost" onClick={() => setRetry(value => value + 1)}>Retry</Button></p>}
      {!data && !error && <Skeleton variant="list" rows={3} />}
      {data && <>{id !== 'ungrouped' && <Link className={buttonStyles({ variant: 'secondary', size: 'sm' })} to={practiceLink({ context_id: context || data.topic.context_id || undefined, topic_id: id, topic: data.topic.name })}>Practise a sample of this topic</Link>}
        {!data.items.length && <p className="text-sm text-muted">No matching subskills. Clear the search to see this topic.</p>}
        <ul className="divide-y divide-border">{data.items.map(skill => <li key={skill.concept_id} className="space-y-2 py-3"><div className="flex flex-wrap items-start justify-between gap-2"><p className="font-medium text-heading">{skill.name}</p><span className="text-xs text-muted">{progressStatus(skill.knowledge_status)}</span></div>{skill.ability && <p className="text-sm text-muted">{skill.ability}</p>}<div className="flex flex-wrap gap-2"><Button variant="ghost" size="sm" onClick={() => setEvidence(skill.concept_id)}>What is this based on?</Button><Link className={buttonStyles({ variant: 'secondary', size: 'sm' })} to={practiceLink({ context_id: context || skill.context_id || data.topic.context_id || undefined, topic_id: id === 'ungrouped' ? undefined : id, concept_ids: [skill.concept_id], topic: skill.name })}>Practise this skill</Link></div>{id !== 'ungrouped' && <MoveSubskill topic={data.topic} skill={skill.concept_id} context={context} onMoved={value => { setLastMove(value); setRetry(count => count + 1); invalidatePageCache(['learning'], true); }} />}</li>)}</ul>
        {data.total > 10 && <Pagination page={Math.floor(data.offset / data.limit) + 1} pages={Math.ceil(data.total / data.limit)} onChange={setPage} label="Topic subskills" />}
      </>}
    </div>
  </Dialog>;
}
