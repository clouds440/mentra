export interface ChoiceOption { id: string; label: string }
export type ChoiceKind = 'single_choice' | 'multiple_choice';
export interface ChoiceCardData {
  id: string; kind: ChoiceKind; question: string;
  options: ChoiceOption[]; selected: string[]; submitted_turn_id: string | null;
}
export interface InteractionResponse { message_id: string; interaction_id: string; selected: string[] }
