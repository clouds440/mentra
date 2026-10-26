import { useEffect, useState } from 'react';
import { assessments } from '../../services/assessments';
import type { ChatAssessmentCardData } from '../../types/assessments';
import { ChatAssessmentCard } from '../assessments/ChatAssessmentCard';
import { AssessmentGenerationCard } from '../assessments/AssessmentGenerationCard';
import { Skeleton } from '../ui/Skeleton';

export interface AssessmentReference { kind: 'draft' | 'saved' | 'generation'; id: string; title: string }

/** Read through the normal owned API; activity never carries private answers. */
export function AssessmentPreview({ reference, conversationId }: { reference: AssessmentReference; conversationId: string }) {
  const [card, setCard] = useState<ChatAssessmentCardData>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setCard(undefined); setFailed(false);
    if (reference.kind === 'generation') return;
    const controller = new AbortController();
    const read = reference.kind === 'draft' ? assessments.draft(reference.id, controller.signal)
      : assessments.detail(reference.id, controller.signal).then(assessment => ({ id: null, conversation_id: conversationId, assessment_id: assessment.id, assessment }));
    void read.then(value => { if (!controller.signal.aborted) setCard(value); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [reference.id, reference.kind, conversationId]);
  if (reference.kind === 'generation') return <AssessmentGenerationCard id={reference.id} title={reference.title} />;
  if (failed) return <p className="mt-3 text-sm text-muted" role="status">Your practice is saved. Its card will appear with the completed response.</p>;
  return card ? <ChatAssessmentCard initial={card} hydrated /> : <Skeleton variant="card" />;
}
