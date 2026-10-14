export type QuestionFormat = string;
export interface PaperSection { title: string; question_count: number; question_type: string; part_marks: number[]; instructions?: string; questions?: { number: number; context: string; parts: { path: string[]; question_type: string; answer_mode: string; marks: number; brief: string }[] }[] }
export interface PaperInfo { duration_minutes: number | null; total_marks: number; question_count: number; instructions: string; sections: PaperSection[] }
export interface AssessmentQuestion { answer_mode?: 'text' | 'single_choice' | 'multiple_choice' | null; context?: string; question_type?: string | null; section?: string | null; number?: number | null; part?: string | null; options?: import('./interactions').ChoiceOption[]; id: string; prompt: string; concept_ids: string[]; difficulty: number; marks: number; source_tokens: string[] }
export interface Assessment { preferences?: { level?: string | null; result_style?: 'marks' | 'grade' | 'feedback' }; paper?: PaperInfo | null; id: string; context_id: string; title: string; purpose: string; revision: number; created_at: string; questions: AssessmentQuestion[]; sources: import('./rag').SourceReference[] }
export interface QuestionGrade { question_id: string; score: number; confidence: number; feedback: string; concept_grades: Record<string, { score: number; max_score: number; confidence: number }>; misconceptions: string[]; outcome?: 'correct' | 'partial' | 'wrong' | null; correct_answer?: string | null }
export interface AssessmentAttempt {
  id: string; assessment_id: string; revision: number; state: 'draft' | 'pending_transcription' | 'submitted' | 'grading' | 'graded' | 'failed';
  attempt_number: number; answers: Record<string, string>; grades: QuestionGrade[] | null;
  extraction: { answers: Record<string, string>; text: string; warnings: string[]; extraction_confidence: number | null; mapping_confidence: number | null; reader_revision: string; truncated: boolean; handwriting_support?: string } | null;
  error: string | null; evidence_status: 'pending' | 'applied' | 'partial' | 'unavailable' | 'none'; created_at: string;
  retry_pending?: boolean;
  assistance?: 'unknown' | 'independent' | 'assisted';
  grade_revision: number; grade_history: { grade_revision: number; grades: QuestionGrade[]; answers: Record<string,string>; corrected_at: string }[];
}
export interface AssessmentGeneration { level?: string; result_style?: 'marks' | 'grade' | 'feedback'; instructions?: string; question_format?: QuestionFormat; duration_minutes?: number; total_marks?: number; client_request_id: string; context_id: string; topic: string; concept_names: string[]; confirm_new_concepts: boolean; count: number | null; purpose: string; grounded: boolean; document_ids: string[] }
export interface GenerationJob { id: string; state: 'queued' | 'running' | 'completed' | 'failed'; title: string; completed_parts: number; total_parts: number | null; result: Assessment | ChatAssessmentCardData | null; error: string | null; can_retry: boolean }
export interface GenerationCardData { id: string; generation_job_id: string; title: string }
export interface ChatAssessmentCardData {
  id: string | null;
  conversation_id: string;
  assessment_id: string | null;
  assessment: Assessment;
  attempt_id?: string;
  deleted?: boolean;
}
