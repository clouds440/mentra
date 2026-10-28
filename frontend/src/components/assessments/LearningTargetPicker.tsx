import { useEffect, useState } from 'react';
import { Button, Input, Pagination } from '../ui';
import { learningTopics, topicSubskills } from '../../services/learning';
import type { LearningTopicsPage, TopicSkillsPage } from '../../types/learning';
import type { AssessmentGeneration } from '../../types/assessments';

export function LearningTargetPicker({ draft, onChange, disabled }: { draft: AssessmentGeneration; onChange: (value: AssessmentGeneration) => void; disabled: boolean }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [topics, setTopics] = useState<LearningTopicsPage>();
  const [skills, setSkills] = useState<TopicSkillsPage>();
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState(!!draft.topic_id);
  useEffect(() => {
    if (search.trim() === query) return;
    const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 250);
    return () => clearTimeout(timer);
  }, [search, query]);
  useEffect(() => { setSearch(''); setQuery(''); setPage(1); setOpen(!!draft.topic_id); }, [draft.topic_id]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setError(''); setTopics(undefined); setSkills(undefined);
    if (draft.topic_id) {
      void topicSubskills(draft.topic_id, controller.signal, draft.context_id, query, (page - 1) * 10)
        .then(value => { if (!controller.signal.aborted) setSkills(value); })
        .catch(() => { if (!controller.signal.aborted) setError('Couldn’t load these skills. Please retry.'); });
    } else {
      void learningTopics(controller.signal, draft.context_id, query, (page - 1) * 10)
        .then(value => { if (!controller.signal.aborted) setTopics(value); })
        .catch(() => { if (!controller.signal.aborted) setError('Couldn’t load saved topics. You can still enter a new topic above.'); });
    }
    return () => controller.abort();
  }, [open, draft.topic_id, draft.context_id, query, page, retry]);
  const selection = draft.concept_ids ?? [];
  const data = skills ?? topics;
  return <details open={open} onToggle={event => setOpen(event.currentTarget.open)} className="rounded-panel border border-border p-3">
    <summary className="ui-disclosure cursor-pointer text-sm font-medium text-heading">{draft.topic_id ? 'Choose subskills · optional' : 'Choose a saved topic · optional'}</summary>
    <div className="mt-3 space-y-3">
      {draft.topic_id && <><p className="text-sm text-heading">{skills?.topic.name ?? draft.topic}</p><p className="text-xs text-muted">Leave subskills unselected for a useful sample. Selecting skills fixes the targets; other skills remain untested.</p><Button size="sm" variant="ghost" disabled={disabled} onClick={() => onChange({ ...draft, topic_id: undefined, concept_ids: [] })}>Choose another saved topic</Button></>}
      <Input type="search" aria-label={draft.topic_id ? 'Find subskills to practise' : 'Find saved topics'} placeholder={draft.topic_id ? 'Find a subskill…' : 'Find a topic…'} value={search} maxLength={200} disabled={disabled} onChange={event => setSearch(event.target.value)} />
      {error && <p role="alert" className="text-xs text-danger">{error} <Button variant="ghost" size="sm" onClick={() => setRetry(value => value + 1)}>Retry</Button></p>}
      {!data && !error && <p role="status" className="text-xs text-muted">Loading…</p>}
      {topics && <ul className="divide-y divide-border">{topics.items.map(topic => <li key={topic.id} className="py-2"><Button variant="ghost" disabled={disabled} className="h-auto w-full justify-start text-left" onClick={() => onChange({ ...draft, topic: topic.name, topic_id: topic.id, context_id: topic.context_id ?? draft.context_id, concept_ids: [] })}>{topic.name}<span className="ml-2 text-xs text-muted">{topic.subskill_count} subskills</span></Button></li>)}</ul>}
      {skills && <fieldset disabled={disabled} className="space-y-2"><legend className="sr-only">Subskills to practise</legend>{skills.items.map(skill => <label key={skill.concept_id} className="flex min-h-11 items-center gap-3 rounded-control border border-border p-3 text-sm text-heading"><input type="checkbox" className="accent-accent" checked={selection.includes(skill.concept_id)} disabled={disabled || !selection.includes(skill.concept_id) && selection.length >= 20} onChange={() => onChange({ ...draft, concept_ids: selection.includes(skill.concept_id) ? selection.filter(id => id !== skill.concept_id) : [...selection, skill.concept_id] })} />{skill.name}</label>)}</fieldset>}
      {data && !data.items.length && <p className="text-xs text-muted">No matches. Try another term or enter a new topic above.</p>}
      {!!selection.length && <p className="text-xs text-muted">{selection.length} selected subskills. Choose at least that many questions.</p>}
      {data && data.total > 10 && <Pagination page={Math.floor(data.offset / data.limit) + 1} pages={Math.ceil(data.total / data.limit)} onChange={setPage} label="Practice targets" />}
    </div>
  </details>;
}
