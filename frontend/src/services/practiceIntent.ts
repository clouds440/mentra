import type { AssessmentGeneration, PracticeIntent } from '../types/assessments';

/** Navigation only prepares an editable draft; generating is an explicit action. */
export function practiceLink(intent: PracticeIntent): string {
  const params = new URLSearchParams({ tab: 'create' });
  if (intent.context_id) params.set('context', intent.context_id);
  if (intent.topic) params.set('topic', intent.topic);
  if (intent.purpose) params.set('purpose', intent.purpose);
  intent.concept_ids?.forEach(id => params.append('concept', id));
  intent.document_ids?.forEach(id => params.append('document', id));
  return `/assessments?${params}`;
}

export function practiceDraft(params: URLSearchParams): AssessmentGeneration {
  const documents = [...new Set(params.getAll('document'))].slice(0,20), concepts = [...new Set(params.getAll('concept'))].slice(0,20);
  const preset = documents.length > 0 || concepts.length > 0;
  return { client_request_id: crypto.randomUUID(), context_id: (params.get('context') ?? '').slice(0,100), topic: (params.get('topic') ?? '').slice(0,200),
    concept_names: [], concept_ids: concepts, confirm_new_concepts: false, count: preset ? 3 : null,
    question_format: preset ? 'mcq' : 'auto', purpose: params.get('purpose') === 'verification' ? 'verification' : 'practice',
    grounded: documents.length > 0, document_ids: documents };
}
