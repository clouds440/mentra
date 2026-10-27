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
export interface ValueBarData { label: string; value: number; max: number; unit?: string; note?: string }
export interface ValueBarsCardData { id: string; kind: 'value_bars'; question: string; bars: ValueBarData[] }
export type InteractionCardData = ChoiceCardData | InputCardData | ValueBarsCardData;
export interface InteractionResponse {
  message_id: string; interaction_id: string; selected?: string[];
  option_inputs?: Record<string, string>; values?: Record<string, string>;
}
export interface InteractionDraft { selected: string[]; optionInputs: Record<string, string>; values: Record<string, string> }
export function isChoice(card: InteractionCardData): card is ChoiceCardData {
  return card.kind === 'single_choice' || card.kind === 'multiple_choice';
}
