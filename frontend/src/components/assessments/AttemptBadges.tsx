import { CheckCircle2, XCircle } from 'lucide-react';
import type { Assessment } from '../../types/assessments';

export function AttemptBadges({ summary }: { summary: Assessment['attempt_summary'] }) {
  if (!summary?.count) return <span className="mt-2 block text-xs text-muted"><span className="workspace-status">No attempts yet</span></span>;
  if (!summary.graded_attempt_id) return <span className="mt-2 block text-xs text-muted"><span className="workspace-status">{summary.latest_state === 'draft' ? 'Attempt in progress' : summary.latest_state === 'failed' ? 'Grading needs attention' : 'Awaiting grading'}</span></span>;
  return <span className="mt-3 block space-y-1.5">
    <span className="flex flex-wrap gap-2">
      <span className="inline-flex items-center gap-1 rounded-full border border-success/25 bg-success/10 px-2 py-1 text-xs font-medium text-success"><CheckCircle2 size={13} aria-hidden="true" />{summary.correct} correct</span>
      <span title={summary.partial ? `Includes ${summary.partial} partially correct answers` : undefined} className="inline-flex items-center gap-1 rounded-full border border-danger/25 bg-danger/10 px-2 py-1 text-xs font-medium text-danger"><XCircle size={13} aria-hidden="true" />{summary.incorrect} incorrect</span>
    </span>
    <span className="block text-[11px] text-subtle">Latest graded attempt{summary.partial ? ` · ${summary.partial} partially correct` : ''}</span>
  </span>;
}
