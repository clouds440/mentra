import { PageSection } from '../workspace/PageShell';
import { buttonStyles } from '../ui/Button';
import { ArrowUpRight, Compass } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { LearningOverview } from '../../types/learning';
import { practiceLink } from '../../services/practiceIntent';
import { progressReason, supportedReview } from './progressLabels';

export function LearningSuggestions({learning, context}: {learning: LearningOverview; context: string}) {
  const reviews = learning.verification.filter(item => supportedReview(item.reason));
  return <>
    <section aria-labelledby="study-next-title" className="space-y-4">
      <div><h2 id="study-next-title" className="flex items-center gap-2 text-lg font-medium text-heading"><Compass size={19} aria-hidden="true" />What to study next</h2>
        <p className="mt-1 text-sm text-muted">Suggested practice based on your learning topics and available answers. New topics can appear here to help you get started.</p></div>
      <ul className="workspace-grid">{learning.recommendations.map(item => <li key={item.concept_id} className="workspace-item flex flex-col gap-3">
        <p className="font-medium text-heading">{item.topic_name ?? item.name}</p>{item.topic_name && <p className="text-sm text-heading">Focus: {item.name}</p>}<p className="text-sm text-muted">{progressReason(item.reason)}</p>
        <Link className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'mt-auto self-start' })} to={practiceLink({ context_id: context || item.context_id, topic_id: item.topic_id ?? undefined, concept_ids: [item.concept_id], topic: item.name, purpose: 'practice' })}>Practise this skill<ArrowUpRight size={14} aria-hidden="true" /></Link>
      </li>)}</ul>
      {!learning.recommendations.length && <p className="text-sm text-muted">Practice suggestions will appear as you explore topics.</p>}
    </section>
    {!!reviews.length && <PageSection aria-labelledby="check-understanding-title" className="workspace-panel space-y-3">
      <div><h2 id="check-understanding-title" className="text-lg font-medium text-heading">Check your understanding</h2>
        <p className="mt-1 text-sm text-muted">You’ve already practised these topics. A short follow-up can help clarify mixed answers or refresh what you remember. These are suggestions, not failed assessments.</p></div>
      <ul className="divide-y divide-border">{reviews.map(item => <li key={item.concept_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
        <div className="min-w-0 flex-1"><p className="font-medium text-heading">{item.name}</p><p className="mt-1 text-sm text-muted">{progressReason(item.reason)}</p></div>
        <Link className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'max-w-full text-left' })} to={practiceLink({ context_id: context || item.context_id, concept_ids: [item.concept_id], topic: item.name, purpose: 'verification' })}>Check this topic<ArrowUpRight size={14} aria-hidden="true" /></Link>
      </li>)}</ul>
    </PageSection>}
  </>;
}
