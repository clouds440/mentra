import { PageSection } from '../workspace/PageShell';
import { Link } from 'react-router-dom';
import { buttonStyles } from '../ui/Button';
import { practiceLink } from '../../services/practiceIntent';
import type { LearningOverview } from '../../types/learning';
import { progressReason, supportedReview } from './progressLabels';

export function QuickReview({ learning, context }: { learning: LearningOverview; context: string }) {
  const target = learning.verification.find(item => supportedReview(item.reason) && (context || item.context_id));
  if (!target) return null;
  return <PageSection aria-label="Quick review" className="workspace-panel flex flex-wrap items-center justify-between gap-4">
    <div><h2 className="font-medium text-heading">Quick review</h2><p className="mt-1 text-sm text-muted">3 short questions on {target.name}.</p><p className="mt-1 text-xs text-muted">{progressReason(target.reason)}</p></div>
    <Link className={buttonStyles({ variant: 'secondary' })} to={practiceLink({ context_id: context || target.context_id, concept_ids: [target.concept_id], topic: target.name, purpose: 'verification' })}>Start quick review</Link>
  </PageSection>;
}
