import { useEffect, useRef, useState } from 'react';
import { FileUp } from 'lucide-react';
import { Button } from '../ui';
import { ApiError } from '../../services/api';
import { assessments } from '../../services/assessments';
import type { AssessmentAttempt, AssessmentAssistance } from '../../types/assessments';

export const answerSheetAccept = '.pdf,.txt,.png,.jpg,.jpeg,application/pdf,text/plain,image/png,image/jpeg';

/** Both quiz and written surfaces enter the same extraction/review pipeline. */
export function AnswerSheetUpload({attempt, onStart, onChange, disabled = false, draftAnswers, onBusyChange, assistance}: {
  attempt: AssessmentAttempt | null; onStart?: (signal: AbortSignal) => Promise<AssessmentAttempt>;
  onChange: (attempt: AssessmentAttempt) => void; disabled?: boolean; draftAnswers?: Record<string,string>; onBusyChange?: (busy: boolean) => void; assistance?: AssessmentAssistance;
}) {
  const input = useRef<HTMLInputElement>(null), active = useRef<AbortController>();
  const working = useRef(attempt), lock = useRef(false), retry = useRef<File>();
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => { working.current = attempt; }, [attempt]);
  useEffect(() => () => active.current?.abort(), []);
  async function upload(file: File) {
    if (lock.current || disabled) return;
    lock.current = true; retry.current = file; setBusy(true); onBusyChange?.(true); setError('');
    const controller = new AbortController(); active.current = controller;
    try {
      if (!working.current) {
        if (!onStart) throw new Error('No attempt');
        working.current = await onStart(controller.signal);
      }
      const answers = Object.fromEntries(Object.entries(draftAnswers ?? working.current.answers).filter(([,answer]) => answer?.trim()));
      if (working.current.state === 'draft' && (JSON.stringify(answers) !== JSON.stringify(working.current.answers) || assistance !== undefined && assistance !== working.current.reported_assistance)) {
        working.current = await assessments.saveDraft(working.current, answers, controller.signal, assistance);
      }
      const result = await assessments.paper(working.current, file, controller.signal);
      if (!controller.signal.aborted) { working.current = result; onChange(result); retry.current = undefined; }
    } catch (reason) {
      if (!controller.signal.aborted) {
        if (attempt && working.current && working.current !== attempt) onChange(working.current);
        setError(reason instanceof ApiError ? reason.message : 'Could not read the answer sheet. Your existing answers are kept.');
      }
    } finally { lock.current = false; if (!controller.signal.aborted) { setBusy(false); onBusyChange?.(false); } }
  }
  return <div className="space-y-2">
    <input type="file" ref={input} className="hidden" aria-label="Upload assessment answer sheet" accept={answerSheetAccept} disabled={disabled || busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void upload(file); }} />
    <Button variant="secondary" size="sm" disabled={disabled || busy} loading={busy} onClick={() => input.current?.click()}><FileUp size={15} aria-hidden="true" />Upload answersheet</Button>
    <p className="text-xs text-muted">PDF, TXT or PNG/JPEG. Review the extracted answers, then submit for evaluation.</p>
    {busy && <p role="status" className="text-xs text-muted">Reading your answer sheet…</p>}
    {error && <div role="alert" className="text-sm text-danger">{error} <Button size="sm" variant="ghost" disabled={disabled || busy} onClick={() => { if (retry.current) void upload(retry.current); }}>Retry upload</Button></div>}
  </div>;
}
