export interface ChoiceOption { id: string; label: string }
export type ChoiceKind = 'single_choice' | 'multiple_choice';
export interface TextInputDefinition {
  kind: 'short_text' | 'long_text'; label: string; placeholder?: string; required?: boolean; max_length?: number;
}
export interface InputFieldDefinition extends Omit<TextInputDefinition, 'kind'> {
  id: string; kind: 'short_text' | 'long_text' | 'number' | 'select';
  minimum?: number | null; maximum?: number | null; options?: ChoiceOption[];
}
export interface ChoiceCardData {
  id: string; kind: ChoiceKind; question: string;
  options: (ChoiceOption & { input?: TextInputDefinition | null })[];
  selected: string[]; option_inputs?: Record<string, string>; submitted_turn_id: string | null;
}
export interface InputCardData {
  id: string; kind: 'text_input' | 'form'; question: string;
  fields: InputFieldDefinition[]; values?: Record<string, string>; submitted_turn_id: string | null;
}
export interface ValueBarData { label: string; value: number; max: number; unit?: string; note?: string; group?: string; series?: string; color?: import('../lib/visualColors').VisualColor | null }
export interface ValueBarsCardData { id: string; kind: 'value_bars'; question: string; bars: ValueBarData[] }
export interface QuestionAnswer { selected?: string[]; option_inputs?: Record<string, string>; values?: Record<string, string> }
export type ConversationQuestion = { id: string; question: string } & (
  { kind: ChoiceKind; options: ChoiceCardData['options'] } |
  { kind: 'short_text' | 'long_text'; required?: boolean; max_length?: number }
);
export interface QuestionnaireCardData {
  id: string; kind: 'questionnaire'; question: string; questions: ConversationQuestion[];
  answers: Record<string, QuestionAnswer>; submitted_turn_id: string | null;
}
export type InteractionCardData = ChoiceCardData | InputCardData | ValueBarsCardData | QuestionnaireCardData;
export interface InteractionSubmission extends QuestionAnswer {
  interaction_id: string; answers?: Record<string, QuestionAnswer>;
}
export interface InteractionResponse extends InteractionSubmission {
  message_id: string; additional_responses?: InteractionSubmission[]; selected?: string[];
  option_inputs?: Record<string, string>; values?: Record<string, string>;
}
export interface InteractionDraft { selected: string[]; optionInputs: Record<string, string>; values: Record<string, string> }
export function isChoice(card: InteractionCardData): card is ChoiceCardData {
  return card.kind === 'single_choice' || card.kind === 'multiple_choice';
}
