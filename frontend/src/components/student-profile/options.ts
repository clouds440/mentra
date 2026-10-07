import type { EducationLevel, ProfileDetails, Dimension } from '../../types/studentProfile';

export const educationLevels: { value: EducationLevel; label: string }[] = [
  { value: 'primary', label: 'Primary' }, { value: 'middle_school', label: 'Middle School' },
  { value: 'high_school', label: 'High School / Secondary' }, { value: 'college', label: 'College / Intermediate' },
  { value: 'undergraduate', label: 'Undergraduate' }, { value: 'graduate', label: 'Graduate' }, { value: 'other', label: 'Other' },
];
export const preferences: { value: ProfileDetails['learning_preference']; label: string }[] = [
  { value: 'balanced', label: 'Balanced' }, { value: 'concise', label: 'Concise / direct' },
  { value: 'examples_first', label: 'Examples first' }, { value: 'step_by_step', label: 'Step by step' },
  { value: 'conceptual', label: 'Conceptual / deep' },
];
export const depths: { value: ProfileDetails['explanation_depth']; label: string }[] = [
  { value: 'brief', label: 'Brief' }, { value: 'standard', label: 'Standard' },
  { value: 'deep', label: 'Deep' },
];
export const dimensionLabels: Record<Dimension, string> = {
  overall_proficiency: 'Overall proficiency', reasoning: 'Reasoning', quantitative: 'Quantitative reasoning',
  comprehension: 'Comprehension', domain_familiarity: 'Domain familiarity',
};
