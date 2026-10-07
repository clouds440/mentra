export type EducationLevel = 'primary' | 'middle_school' | 'high_school' | 'college' | 'undergraduate' | 'graduate' | 'other';
export interface ProfileDetails {
  education_level: EducationLevel;
  field_of_study: string;
  learning_goal: string;
  learning_preference: 'balanced' | 'concise' | 'examples_first' | 'step_by_step' | 'conceptual';
  explanation_depth: 'brief' | 'standard' | 'deep';
}
export type Dimension = 'overall_proficiency' | 'reasoning' | 'quantitative' | 'comprehension' | 'domain_familiarity';
export interface ProfileEstimate {
  value: number | null;
  confidence: number;
  evidence_count: number;
  source_count: number;
  effective_weight: number;
  successful_weight: number;
  last_evidence_at: string | null;
  rationale: string | null;
}
export interface StudentProfile {
  learner_id: string;
  details: ProfileDetails | null;
  details_source: string | null;
  estimates: Record<Dimension, ProfileEstimate>;
  onboarding_phase: 'information' | 'calibration' | 'complete';
  calibration_status: 'not_started' | 'in_progress' | 'skipped' | 'completed';
  evaluation_status: 'not_started' | 'pending' | 'evaluating' | 'applied' | 'failed' | 'superseded';
  version: number;
  context_version: number;
  created_at: string;
  updated_at: string;
}
export interface CalibrationQuestion {
  id: string;
  prompt: string;
  kind: 'mcq' | 'true_false' | 'selection';
  options: { id: string; text: string }[];
}
export interface CalibrationAttempt {
  id: string;
  blueprint_version: string;
  questions: CalibrationQuestion[];
  answers: Record<string, string>;
  status: 'in_progress' | 'completed' | 'skipped' | 'superseded';
  version: number;
}
