import { BookOpen, Sparkles } from 'lucide-react';
import { Button, FormField, Input, Textarea } from '../ui';
import { MaterialPicker, materialSelectionKey } from '../library/MaterialPicker';
import type { AssessmentGeneration } from '../../types/assessments';
import { useId, useState } from 'react';

const formats = [
  ['mcq', 'Multiple choice'], ['multiple_select', 'Multiple select'],
  ['true_false', 'True / false'], ['short_answer', 'Short answers'],
  ['written', 'Written responses'], ['numerical', 'Numerical'],
  ['fill_blank', 'Fill in the blanks'], ['matching', 'Matching'],
  ['ordering', 'Ordering'], ['essay', 'Essays'], ['proof', 'Proofs'], ['case_study', 'Case studies'],
] as const;

export function AssessmentCreateForm({ draft, onChange, busy, onSubmit, topics }: {
  topics: string[]; draft: AssessmentGeneration; onChange: (draft: AssessmentGeneration) => void;
  busy: boolean; onSubmit: () => void;
}) {
  const topicList = useId();
  const [validity, setValidity] = useState<{ key: string; ready: boolean }>();
  const selected = draft.question_formats ?? (draft.question_format && !['auto', 'mixed', 'mock_paper'].includes(draft.question_format) ? [draft.question_format] : []);
  const invalidCount = !!draft.count && draft.count < selected.length;
  const materialsReady = !draft.document_ids.length || validity?.ready && validity.key === materialSelectionKey(draft.document_ids, draft.context_id);
  return <form aria-label="Create assessment" className="workspace-panel max-w-3xl space-y-6" onSubmit={event => { event.preventDefault(); if (draft.topic.trim() && !invalidCount && materialsReady) onSubmit(); }}>
    <FormField label="Topic">{field => <Input {...field} list={topicList} required maxLength={200} placeholder="What would you like to practise?" value={draft.topic} disabled={busy} onChange={event => onChange({ ...draft, topic: event.target.value, concept_ids: [], context_id: '' })} />}</FormField>
    <datalist id={topicList}>{[...new Set(topics)].map(topic => <option key={topic} value={topic} />)}</datalist>
    {!!draft.concept_ids?.length && <p className="text-xs text-muted">Practising {draft.concept_ids.length} selected topic{draft.concept_ids.length === 1 ? '' : 's'} in this learning context.</p>}
    <details className="rounded-panel border border-border p-3" open={draft.document_ids.length > 0 || undefined}>
      <summary className="cursor-pointer text-sm font-medium text-heading"><BookOpen size={16} className="mr-2 inline" aria-hidden="true" />Study materials <span className="font-normal text-muted">· optional</span></summary>
      <div className="mt-4"><MaterialPicker value={draft.document_ids} contextId={draft.context_id} disabled={busy} onValidityChange={setValidity} onChange={document_ids => onChange({ ...draft, document_ids, grounded: document_ids.length > 0 })} /></div>
    </details>
    <FormField label="What should it include?" hint="Add anything that matters: subtopics, level, examples or exam requirements.">{field => <Textarea {...field} aria-label="Assessment instructions" rows={3} maxLength={4000} disabled={busy} placeholder="For example: focus on Newton’s laws, with everyday examples and a few calculations." value={draft.instructions ?? ''} onChange={event => onChange({ ...draft, instructions: event.target.value })} />}</FormField>
    <fieldset disabled={busy} className="space-y-3">
      <legend className="text-sm font-medium text-heading">Question formats</legend>
      <p className="text-xs text-muted">Select any combination, or leave these empty for Mentra to choose.</p>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">{formats.map(([value, label]) => <label key={value} className={`flex min-h-11 cursor-pointer items-center rounded-control border px-3 py-2 text-sm transition-colors ${selected.includes(value) ? 'border-accent bg-active text-heading' : 'border-border text-muted hover:bg-hover'}`}><input type="checkbox" className="mr-2 h-4 w-4 shrink-0 accent-accent focus-visible:ring-2 focus-visible:ring-accent" checked={selected.includes(value)} onChange={() => { const next = selected.includes(value) ? selected.filter(item => item !== value) : [...selected, value]; onChange({ ...draft, question_formats: next, question_format: next.length === 1 ? next[0] : next.length ? 'mixed' : 'auto' }); }} /><span>{label}</span></label>)}</div>
    </fieldset>
    <div className="max-w-xs"><FormField label="Number of questions" error={invalidCount ? 'Choose at least one question per selected format.' : undefined}>{field => <Input {...field} aria-label="Number of questions" type="number" min={Math.max(1, selected.length)} max={20} step={1} required disabled={busy} value={draft.count ?? ''} onChange={event => onChange({ ...draft, count: event.target.value ? Number(event.target.value) : null })} />}</FormField><p className="mt-2 text-xs text-muted">Up to 20 questions.</p></div>
    <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4"><Button type="submit" loading={busy} disabled={busy || !draft.topic.trim() || invalidCount || !materialsReady}><Sparkles size={16} aria-hidden="true" />Generate assessment</Button><p className="max-w-sm text-xs leading-5 text-muted">Mentra adapts the difficulty, marking and structure to your request and learning profile.</p></div>
  </form>;
}
