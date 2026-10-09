export interface LearningConcept {
  concept_id: string; name: string; mastery: number | null; estimate_confidence: number | null;
  retention_confidence: number | null; knowledge_status: string; misconceptions: string[];
}
export interface LearningOverview {
  learner: { concepts: LearningConcept[]; generated_at: string; context_ids: string[] };
  recommendations: { concept_id: string; name: string; reason: string; knowledge_status: string; recommended_difficulty: number }[];
  verification: { concept_id: string; name: string; reason: string }[];
}
