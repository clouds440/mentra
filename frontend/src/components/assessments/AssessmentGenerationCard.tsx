import { useEffect, useRef, useState } from 'react';
import { FileText, CheckCircle2 } from 'lucide-react';
import { Button, Spinner } from '../ui';
import { ProgressBar } from '../ui/ProgressBar';
import { assessments } from '../../services/assessments';
import { assessmentGeneration, useAssessmentGeneration } from '../../stores/assessmentGeneration';
import type { GenerationJob, Assessment, ChatAssessmentCardData } from '../../types/assessments';
import { ChatAssessmentCard } from './ChatAssessmentCard';

export function AssessmentGenerationCard({ id, title, onComplete }: { id: string; title: string; onComplete?: (result: Assessment | ChatAssessmentCardData) => void }) {
  const { job, error: progressError, unavailable, receivedAt } = useAssessmentGeneration(id);
  const [error, setError] = useState('');
  const [retrying, setRetrying] = useState(false);
  const completed = useRef(false), callback = useRef(onComplete); callback.current = onComplete;
  const retryController = useRef<AbortController>(undefined);
  useEffect(() => { completed.current = false; return () => retryController.current?.abort(); }, [id]);
  useEffect(() => {
    if (job?.state === 'completed' && job.result && !completed.current) {
      completed.current = true; callback.current?.(job.result);
    }
  }, [job]);
  function publish(value: GenerationJob) { assessmentGeneration.accept(id, value); }
  async function retry() {
    if (retrying) return;
    const controller = new AbortController(); retryController.current = controller; setRetrying(true);
    try { const value = await assessments.retryJob(id, controller.signal); if (!controller.signal.aborted) { publish(value); assessmentGeneration.refresh(id); } }
    catch { if (!controller.signal.aborted) setError('Could not resume generation. Try again.'); }
    finally { if (!controller.signal.aborted) setRetrying(false); }
  }
  async function stop() {
    if (retrying || !job) return;
    const controller = new AbortController(); retryController.current = controller; setRetrying(true);
    try { const value = await assessments.stopJob(id, job.revision ?? 1, controller.signal); if (!controller.signal.aborted) { publish(value); assessmentGeneration.refresh(id); } }
    catch { if (!controller.signal.aborted) setError('Could not pause generation. Try again.'); }
    finally { if (!controller.signal.aborted) setRetrying(false); }
  }
  if (job?.state === 'completed' && job.result && !onComplete && !unavailable) {
    const initial: ChatAssessmentCardData = 'assessment' in job.result ? job.result
      : { id: null, assessment_id: job.result.id, assessment: job.result, conversation_id: '' };
    return <ChatAssessmentCard initial={{ ...initial, hydration: job.hydration ?? initial.hydration }} hydrated={!!(job.hydration ?? initial.hydration)} receivedAt={receivedAt} />;
  }
  return <section aria-label="Assessment generation" className="my-4 space-y-3 rounded-xl border border-border-strong bg-surface p-4">
    <div className="flex items-start gap-2.5"><FileText size={17} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" /><div className="min-w-0 flex-1"><h2 className="break-words text-sm font-semibold text-heading">{job?.title ?? title}</h2><p role="status" className="mt-1 flex items-center gap-2 text-xs text-muted">{unavailable ? 'Unavailable' : job?.state === 'failed' || job?.state === 'stopped' ? 'Generation paused' : job?.state === 'completed' ? <><CheckCircle2 size={13} />Ready</> : <><Spinner className="h-3 w-3" aria-hidden="true" />{job?.state === 'running' ? 'Building your assessment' : 'Waiting to begin'}</>}</p></div></div>
    {job?.total_parts && <><ProgressBar label="Assessment generation progress" value={job.completed_parts} max={job.total_parts} showValue={false} /><p className="text-xs text-muted">{job.completed_parts} of {job.total_parts} questions or parts ready</p></>}
    <p className="text-xs leading-5 text-subtle">{job?.state === 'stopped' ? job.can_resume ? 'Paused. Resume within 30 minutes to reuse completed batches.' : 'Paused work expired. Start again to create this assessment.' : 'Progress is saved as each batch completes. You can leave this page and return.'}</p>
    {(job?.error || error || progressError) && <p role="alert" className="text-xs text-danger">{job?.error || error || progressError}</p>}
    {job?.can_retry && <Button size="sm" variant="secondary" loading={retrying} onClick={() => void retry()}>{job.state === 'stopped' && !job.can_resume ? 'Start again' : 'Resume generation'}</Button>}
    {job && ['queued','running'].includes(job.state) && <Button size="sm" variant="secondary" loading={retrying} onClick={() => void stop()}>Stop generation</Button>}
  </section>;
}
