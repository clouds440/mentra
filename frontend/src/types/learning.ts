export interface LearningConcept {
  ability?: string | null;
  topic_id?: string | null; topic_name?: string | null; context_id?: string | null;
  concept_id: string; name: string; mastery: number | null; estimate_confidence: number | null;
  retention_confidence: number | null; knowledge_status: string; misconceptions: string[];
}

export interface LearningTopic { id: string; name: string; scope: string; context_id?: string | null; matching_skills?: string[]; subskill_count: number; checked_count: number; revision: number }
export interface LearningTopicsPage { items: LearningTopic[]; total: number; ungrouped_count: number; limit: number; offset: number; generated_at: string }
export interface TopicSkillsPage { topic: LearningTopic; items: LearningConcept[]; total: number; limit: number; offset: number; generated_at: string }
export interface LearningOverview {
  learner: { concepts: LearningConcept[]; generated_at: string; context_ids: string[] };
  recommendations: { topic_id?: string | null; topic_name?: string | null; context_id?: string; concept_id: string; name: string; reason: string; knowledge_status: string; recommended_difficulty: number }[];
  verification: { topic_id?: string | null; topic_name?: string | null; context_id?: string; concept_id: string; name: string; reason: string }[];
}

export interface LearningProgressPage {
  items: LearningConcept[]; total: number; total_concepts: number; limit: number; offset: number;
  generated_at: string;
}
export interface ProgressExplanation {
  context_id?: string | null;
  concept_id: string; name: string; knowledge_status: string; mastery: number | null;
  mastery_lower_bound: number; mastery_upper_bound: number; independent_item_count: number; evidence_count: number;
  last_practice_at: string | null; last_independent_at: string | null; recommended_difficulty: number; next_check: string;
  difficulty_coverage: { band: 'easy' | 'medium' | 'hard'; independent_items: number }[];
  recent_evidence: { occurred_at: string; source_type: string; result: string; difficulty: number | null; independent: boolean;
    participation: 'independent' | 'repeated' | 'assisted' | 'unspecified'; assessment_id: string | null; attempt_id: string | null; grade_revision: number | null; source_available: boolean }[];
  generated_at: string;
}
