export interface AssessmentQuestion { id: string; prompt: string; concept_ids: string[]; difficulty: number; marks: number; source_tokens: string[] }
export interface Assessment { id: string; context_id: string; title: string; purpose: string; revision: number; created_at: string; questions: AssessmentQuestion[]; sources: import('./rag').SourceReference[] }
export interface QuestionGrade { question_id: string; score: number; confidence: number; feedback: string; concept_grades: Record<string, { score: number; max_score: number; confidence: number }>; misconceptions: string[] }
export interface AssessmentAttempt {
  id: string; assessment_id: string; revision: number; state: 'draft' | 'pending_transcription' | 'submitted' | 'grading' | 'graded' | 'failed';
  attempt_number: number; answers: Record<string, string>; grades: QuestionGrade[] | null;
  extraction: { answers: Record<string, string>; text: string; warnings: string[]; extraction_confidence: number | null; mapping_confidence: number | null; reader_revision: string; truncated: boolean } | null;
  error: string | null; evidence_status: 'pending' | 'applied' | 'unavailable' | 'none'; created_at: string;
  grade_revision: number; grade_history: { grade_revision: number; grades: QuestionGrade[]; answers: Record<string,string>; corrected_at: string }[];
}
export interface AssessmentGeneration { client_request_id: string; context_id: string; topic: string; concept_names: string[]; confirm_new_concepts: boolean; count: number; purpose: string; grounded: boolean; document_ids: string[] }
