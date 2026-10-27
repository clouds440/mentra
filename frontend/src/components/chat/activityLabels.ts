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
  web_research: 'Researching your question',
  present_choices: 'Preparing choices for you',
  request_input: 'Preparing a question for you',
  present_visuals: 'Preparing a visual comparison',
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
  assessment_generate_advanced: 'Creating your practice questions',
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
  'Writing your response': 'Putting it together',
  'Reading documents': 'Reading your study material',
};

// These reads are routine prompt preparation, not a distinct user-facing action.
const quietTools = new Set([
  'profile_context', 'get_active_learning_contexts',
  'resolve_student_concept', 'enable_workflow_tools',
]);

const completedLabels: Record<string, string> = {
  web_search: 'Reviewing web results', web_research: 'Reviewing what I found',
  search_study_material: 'Connecting the relevant details', get_study_source_chunk: 'Connecting the relevant details',
  document_extract: 'Working with your attachment', history_lookup: 'Connecting our earlier discussion',
  user_memory: 'Considering what you’ve shared', get_relevant_learner_context: 'Adapting to your progress',
  get_study_recommendations: 'Choosing useful next steps', get_student_weaknesses: 'Choosing useful practice',
  get_verification_candidates: 'Choosing what to review',
  assessment_generate: 'Preparing your practice questions', assessment_revise: 'Preparing the revised questions',
  assessment_generate_advanced: 'Preparing your practice questions',
  assessment_question: 'Working through your question', assessment_status: 'Reviewing your practice progress',
  assessment_answer: 'Preparing your feedback', assessment_lookup: 'Reviewing your practice questions',
  event_lookup: 'Reviewing your schedule', event_manage: 'Reviewing the event details',
  present_choices: 'Preparing your options',
  request_input: 'Preparing your question',
  present_visuals: 'Preparing your comparison',
};

/** null means routine/unknown activity: retain the last meaningful feedback. */
export function activityLabel(activity?: ActivityLabelInput): string | null {
  if (!activity) return 'Thinking';
  if (activity.status === 'waiting') return 'Waiting for your input';
  if (activity.status === 'cancelled') return 'Stopping this response';
  if (activity.step_id === 'protocol-repair') return 'Taking another look';
  if (quietTools.has(activity.tool_name ?? '')) return null;
  if (activity.status === 'failed' || activity.status === 'degraded') {
    if (activity.tool_name === 'web_search' || activity.tool_name === 'web_research') return 'Web search was limited; continuing with available information';
    if (activity.tool_name === 'document_extract') return 'The attachment couldn’t be fully read';
    if (activity.tool_name === 'search_study_material' || activity.tool_name === 'get_study_source_chunk') return 'Study material couldn’t be fully checked';
    if (activity.tool_name === 'event_manage') return 'The event change couldn’t be confirmed';
    if (activity.tool_name === 'assessment_answer') return 'Your answers couldn’t be fully evaluated';
    if (activity.tool_name?.startsWith('assessment_')) return 'This practice step couldn’t be finished';
    if (activity.tool_name && Object.prototype.hasOwnProperty.call(toolLabels, activity.tool_name)) return 'Some information is unavailable; continuing with what I have';
    return null;
  }
  if (activity.status === 'retry_wait') return 'Trying again';
  if (activity.step_id === 'response-stream') return 'Putting it together';
  if (activity.tool_name === 'web_search') {
    if (activity.status === 'completed') return 'Reviewing web results';
    const websites = activity.websites ?? [];
    return websites.length === 1 ? `Searching ${websites[0].domain}` : 'Searching the web';
  }
  if (activity.status === 'completed') return completedLabels[activity.tool_name ?? ''] ?? null;
  return (activity.tool_name && Object.prototype.hasOwnProperty.call(toolLabels, activity.tool_name) ? toolLabels[activity.tool_name] : undefined)
    ?? (Object.prototype.hasOwnProperty.call(messageLabels, activity.user_message) ? messageLabels[activity.user_message] : undefined)
    ?? null;
}
