import type { EducationLevel, ProfileDetails, Dimension } from '../../types/studentProfile';

type Option<T> = { value: T; label: string; description: string };
export const educationLevels: { value: EducationLevel; label: string }[] = [
  { value: 'primary', label: 'Primary' }, { value: 'middle_school', label: 'Middle School' },
  { value: 'high_school', label: 'High School / Secondary' }, { value: 'college', label: 'College / Intermediate' },
  { value: 'undergraduate', label: 'Undergraduate' }, { value: 'graduate', label: 'Graduate' }, { value: 'other', label: 'Other' },
];
export const preferences: Option<ProfileDetails['learning_preference']>[] = [
  { value: 'balanced', label: 'Adaptive', description: 'Mentra chooses the explanation structure that fits your question.' },
  { value: 'examples_first', label: 'Examples first', description: 'Start with a small example, then explain the idea behind it.' },
  { value: 'step_by_step', label: 'Step by step', description: 'Work through solutions and procedures in manageable steps.' },
  { value: 'conceptual', label: 'Concepts and reasoning', description: 'Focus on the core idea, relationships and why things work.' },
];
export const depths: Option<ProfileDetails['explanation_depth']>[] = [
  { value: 'brief', label: 'Brief', description: 'Direct answers with only the essential explanation.' },
  { value: 'standard', label: 'Standard', description: 'Enough explanation and examples to understand the answer.' },
  { value: 'deep', label: 'Detailed', description: 'More reasoning, supporting examples and relevant nuance.' },
];
export const participationOptions: Option<NonNullable<ProfileDetails['participation']>>[] = [
  { value: 'adaptive', label: 'Adaptive', description: 'Mentra invites participation when it would help you learn.' },
  { value: 'interactive', label: 'Interactive', description: 'Learn by doing: make predictions, answer short questions and try small exercises when useful.' },
  { value: 'mostly_explanations', label: 'Mostly explanations', description: 'Prefer explanations without unsolicited exercises or comprehension checks.' },
];
export const visualOptions: Option<NonNullable<ProfileDetails['visual_support']>>[] = [
  { value: 'adaptive', label: 'Adaptive', description: 'Use visuals when they make the answer clearer.' },
  { value: 'prefer_visuals', label: 'Prefer visuals', description: 'Prefer useful diagrams, comparison bars and charts alongside explanations.' },
  { value: 'mostly_text', label: 'Mostly text', description: 'Prefer prose, lists and simple tables over unsolicited diagrams and charts.' },
];
export const purposeOptions: Option<NonNullable<ProfileDetails['learning_purpose']>>[] = [
  { value: 'general', label: 'Let my question guide it', description: 'Follow the goal you describe without assuming a particular purpose.' },
  { value: 'fundamentals', label: 'Understand fundamentals', description: 'Build core ideas and prerequisites when planning what to learn.' },
  { value: 'apply', label: 'Apply or build something', description: 'Connect explanations and plans to practical tasks and applications.' },
  { value: 'exam', label: 'Prepare for an exam', description: 'Focus relevant plans on revision and exam skills. Assessments still need your request.' },
  { value: 'explore', label: 'Explore a subject', description: 'Connect ideas and suggest useful directions when you ask what to learn next.' },
];

/** Adapt old profiles for editing/display; leave stored evidence snapshots intact. */
export function editableDetails(details: ProfileDetails): ProfileDetails {
  return { ...details,
    learning_preference: ['concise', 'interactive'].includes(details.learning_preference) ? 'balanced' : details.learning_preference,
    explanation_depth: details.learning_preference === 'concise' ? 'brief' : details.explanation_depth,
    participation: details.learning_preference === 'interactive' && (!details.participation || details.participation === 'adaptive') ? 'interactive' : details.participation ?? 'adaptive',
    visual_support: details.visual_support ?? 'adaptive', learning_purpose: details.learning_purpose ?? 'general',
  };
}
export const dimensionLabels: Record<Dimension, string> = {
  overall_proficiency: 'Overall proficiency', reasoning: 'Reasoning', quantitative: 'Quantitative reasoning',
  comprehension: 'Comprehension', domain_familiarity: 'Domain familiarity',
};
