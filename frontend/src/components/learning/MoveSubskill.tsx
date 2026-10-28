import { useEffect, useRef, useState } from 'react';
import { Button, Input, Pagination } from '../ui';
import { learningTopics, moveLearningSubskill } from '../../services/learning';
import type { LearningTopic, LearningTopicsPage } from '../../types/learning';

export interface SkillMove { skill: string; target: string; operation: string }

export function MoveSubskill({ topic, skill, context, onMoved }: { topic: LearningTopic; skill: string; context: string; onMoved: (move: SkillMove) => void }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<LearningTopicsPage>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const operation = useRef<AbortController>();
  const receipt = useRef<{ target: string; id: string }>();
  useEffect(() => () => operation.current?.abort(), []);
  useEffect(() => { if (search.trim() === query) return; const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 250); return () => clearTimeout(timer); }, [search, query]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setData(undefined);
    void learningTopics(controller.signal, context, query, (page - 1) * 10).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(() => { if (!controller.signal.aborted) setError('Couldn’t load destination topics.'); });
    return () => controller.abort();
  }, [open, context, query, page]);
  async function move(target: string) {
    if (busy) return;
    const controller = new AbortController(); operation.current = controller; setBusy(true); setError('');
    if (receipt.current?.target !== target) receipt.current = { target, id: crypto.randomUUID() };
    const id = receipt.current.id;
    try {
      await moveLearningSubskill(topic.id, skill, target, topic.revision, id, controller.signal);
      if (!controller.signal.aborted) onMoved({ skill, target, operation: id });
    } catch { if (!controller.signal.aborted) setError('Couldn’t move this skill. Refresh its topic and retry.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <details onToggle={event => setOpen(event.currentTarget.open)} className="text-xs text-muted"><summary className="ui-disclosure cursor-pointer">Change this skill’s topic</summary>{open && <div className="mt-2 space-y-2"><p>Move its placement while preserving all answers and evidence.</p><Input aria-label="Find destination topic" value={search} disabled={busy} onChange={event => setSearch(event.target.value)} maxLength={200} placeholder="Find another topic…" />{error && <p role="alert" className="text-danger">{error}</p>}{!data && <p role="status">Loading topics…</p>}<ul>{data?.items.filter(item => item.id !== topic.id).map(item => <li key={item.id}><Button size="sm" variant="ghost" disabled={busy} onClick={() => void move(item.id)}>Move to {item.name}</Button></li>)}</ul>{data && data.total > 10 && <Pagination page={page} pages={Math.ceil(data.total / data.limit)} onChange={setPage} disabled={busy} label="Destination topics" />}</div>}</details>;
}
