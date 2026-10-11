/** Closed presentation vocabulary: backend tool names/messages never render verbatim. */
export interface ActivityLabelInput {
  tool_name: string | null;
  step_id: string;
  status: string;
  user_message: string;
  websites?: { domain: string }[];
}

const toolLabels: Record<string, string> = {
  web_search: 'Searching the web',
  present_choices: 'Preparing choices for you',
  event_lookup: 'Checking your events',
  event_manage: 'Preparing your event',
  history_lookup: 'Looking back at our conversations',
  user_memory: 'Checking what you’ve shared',
  get_active_learning_contexts: 'Checking what you’re studying',
  get_relevant_learner_context: 'Checking your learning progress',
  get_study_recommendations: 'Finding what to study next',
  get_student_weaknesses: 'Finding useful practice topics',
  get_verification_candidates: 'Finding concepts to review',
  resolve_student_concept: 'Understanding the topic',
  search_study_material: 'Reading your study material',
  get_study_source_chunk: 'Reading the relevant passage',
  assessment_generate: 'Creating your practice questions',
  assessment_revise: 'Revising your practice questions',
  assessment_question: 'Reading your question',
  assessment_status: 'Checking your practice progress',
  assessment_answer: 'Reviewing your answers',
  assessment_lookup: 'Finding your practice questions',
  enable_workflow_tools: 'Preparing to help',
  profile_context: 'Checking your learning preferences',
  document_extract: 'Reading your attachment',
};

const messageLabels: Record<string, string> = {
  'Planning your request': 'Thinking',
  'Preparing your answer': 'Thinking',
  'Writing your response': 'Writing your answer',
  'Reading documents': 'Reading your study material',
};

// These reads are routine prompt preparation, not a distinct user-facing action.
const quietTools = new Set([
  'profile_context', 'get_active_learning_contexts', 'get_relevant_learner_context',
  'resolve_student_concept', 'enable_workflow_tools',
]);

export function activityLabel(activity?: ActivityLabelInput): string {
  if (!activity) return 'Thinking';
  if (activity.status === 'waiting') return 'Waiting for your input';
  if (activity.status === 'cancelled') return 'Stopping this request';
  if (quietTools.has(activity.tool_name ?? '')) return 'Thinking';
  if (activity.status === 'failed' || activity.status === 'degraded') return 'Thinking';
  if (activity.status === 'retry_wait') return 'Trying again';
  if (activity.step_id === 'response-stream') return 'Writing your answer';
  if (activity.step_id === 'protocol-repair') return 'Taking another look';
  if (activity.tool_name === 'web_search') {
    if (activity.status === 'completed') return 'Reviewing web results';
    const websites = activity.websites ?? [];
    return websites.length === 1 ? `Searching ${websites[0].domain}` : 'Searching the web';
  }
  if (activity.status === 'completed') return 'Thinking';
  return (activity.tool_name && Object.prototype.hasOwnProperty.call(toolLabels, activity.tool_name) ? toolLabels[activity.tool_name] : undefined)
    ?? (Object.prototype.hasOwnProperty.call(messageLabels, activity.user_message) ? messageLabels[activity.user_message] : undefined)
    ?? 'Thinking';
}
