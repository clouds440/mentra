import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Toggle } from '../ui';
import { ApiError } from '../../services/api';
import { assessments } from '../../services/assessments';
import type { Assessment, AssessmentAttempt } from '../../types/assessments';
import { questionLabel } from './AssessmentPaper';
import { RotateCcw, ArrowUpRight } from 'lucide-react';

export function MistakePractice({ assessment, attempt }: { assessment: Assessment; attempt: AssessmentAttempt }) {
  const navigate = useNavigate();
  const [partial, setPartial] = useState(false), [selected, setSelected] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [deleted, setDeleted] = useState(false);
  const active = useRef<AbortController>(), lock = useRef(false);
  const operation = useRef<{ payload: string; id: string }>();
  useEffect(() => () => active.current?.abort(), []);
  const grades = new Map(attempt.grades?.map(grade => [grade.question_id, grade]));
  const eligible = assessment.questions.filter(question => {
    const grade = grades.get(question.id);
    return grade && grade.score < question.marks && (partial || grade.score === 0);
  });
  const ids = selected?.filter(id => eligible.some(question => question.id === id)) ?? eligible.slice(0, 20).map(question => question.id);
  async function create() {
    if (lock.current || !ids.length || ids.length > 20) return;
    lock.current = true; setBusy(true); setError('');
    if (deleted) { operation.current = undefined; setDeleted(false); }
    const controller = new AbortController(); active.current = controller;
    const payload = JSON.stringify([attempt.id, attempt.grade_revision, [...ids].sort()]);
    if (operation.current?.payload !== payload) operation.current = { payload, id: crypto.randomUUID() };
    try {
      const result = await assessments.practiseMistakes(attempt, ids, operation.current.id, controller.signal);
      if (!controller.signal.aborted) navigate(`/assessments?assessment=${encodeURIComponent(result.id)}`);
    } catch (reason) { if (!controller.signal.aborted) { setError(reason instanceof ApiError ? reason.message : 'Unable to prepare practice. Try again.'); setDeleted(reason instanceof ApiError && reason.code==='ASSESSMENT_PRACTICE_DELETED'); } }
    finally { lock.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="space-y-4 rounded-panel border border-border bg-surface p-4" aria-label="Practise my mistakes">
    <div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-control bg-active text-accent"><RotateCcw size={18} aria-hidden="true" /></span><div className="min-w-0"><h3 className="text-sm font-semibold text-heading">Practise my mistakes</h3><p className="mt-1 text-xs leading-5 text-muted">Focus on what needs another try. Your original answers and results stay saved.</p></div></div>
    <Toggle label="Include partially correct questions" checked={partial} disabled={busy} onChange={event => { setPartial(event.target.checked); setSelected(null); }} />
    <p role="status" className="text-xs text-muted">{eligible.length} eligible · {ids.length} selected (up to 20)</p>
    {!!eligible.length && <details><summary className="cursor-pointer rounded-control py-1 text-xs font-medium text-accent focus-visible:ring-2 focus-visible:ring-accent">Choose questions</summary><div className="mt-2 grid max-h-64 grid-cols-2 gap-2 overflow-y-auto overscroll-contain sm:grid-cols-3">{eligible.map(question => <label key={question.id} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-control border px-3 py-2 text-xs text-heading ${ids.includes(question.id) ? 'border-accent/40 bg-active' : 'border-border bg-background'}`}><input type="checkbox" className="h-4 w-4 shrink-0 accent-accent focus-visible:ring-2 focus-visible:ring-accent" disabled={busy || !ids.includes(question.id) && ids.length >= 20} checked={ids.includes(question.id)} onChange={event => setSelected(event.target.checked ? [...ids, question.id] : ids.filter(id => id !== question.id))} /><span className="break-words">{questionLabel(question, assessment.questions.indexOf(question))}</span></label>)}</div></details>}
    {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    {eligible.length ? <div className="flex flex-wrap items-center justify-between gap-3"><p className="max-w-sm text-xs leading-5 text-muted">Feedback may have revealed the answers, so this is recorded as repeated practice.</p><Button size="sm" variant="secondary" className="max-sm:w-full" disabled={busy || !ids.length} loading={busy} onClick={() => void create()}>{deleted ? 'Prepare a new follow-up' : 'Prepare mistake practice'}<ArrowUpRight size={14} aria-hidden="true" /></Button></div> : <p className="text-xs text-muted">No incorrect questions to revisit. Include partial answers or create fresh practice from Assessments.</p>}
  </section>;
}
