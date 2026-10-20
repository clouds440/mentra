import { Link } from 'react-router-dom';
import { ArrowUpRight, RotateCcw } from 'lucide-react';
import { buttonStyles } from '../ui';
import type { Assessment, AssessmentAttempt } from '../../types/assessments';

export function MistakePractice({ assessment }: { assessment: Assessment; attempt: AssessmentAttempt }) {
  return <section className="space-y-3 rounded-panel border border-border bg-surface p-4" aria-label="Practice my mistakes">
    <h3 className="flex items-center gap-2 text-sm font-medium text-heading"><RotateCcw size={16} aria-hidden="true" />Practice my mistakes</h3>
    <p className="text-xs leading-5 text-muted">Review mistakes and create fresh revision questions in the Practice my mistakes tab.</p>
    <Link className={buttonStyles({ variant: 'secondary', size: 'sm' })} to={`/assessments?tab=mistakes&mistake_assessment=${encodeURIComponent(assessment.id)}`}>Review these mistakes<ArrowUpRight size={14} aria-hidden="true" /></Link>
  </section>;
}
