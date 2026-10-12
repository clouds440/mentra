import { useId } from 'react';
import type { ReactNode } from 'react';
import type { ChoiceKind, ChoiceOption } from '../../types/interactions';

export interface ChoiceOptionsProps {
  kind: ChoiceKind;
  question: string;
  options: readonly ChoiceOption[];
  selected: readonly string[];
  onChange: (selected: string[]) => void;
  disabled?: boolean;
  hideLegend?: boolean;
  renderLabel?: (label: string) => ReactNode;
}

/** Controlled native selection UI. Callers own persistence and answer submission. */
export function ChoiceOptions({ kind, question, options, selected, onChange, disabled = false, hideLegend = false, renderLabel }: ChoiceOptionsProps) {
  const group = useId();
  return <fieldset disabled={disabled} className="space-y-2">
    <legend className={hideLegend ? 'sr-only' : 'mb-2 font-medium text-heading'}>{question}</legend>
    {options.map(option => <label key={option.id} className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-input p-3 text-sm has-[:checked]:border-accent">
      <input className="mt-1 accent-accent" type={kind === 'single_choice' ? 'radio' : 'checkbox'} name={group} value={option.id}
        checked={selected.includes(option.id)} onChange={event => onChange(kind === 'single_choice' ? [option.id] : event.target.checked ? [...selected.filter(id => id !== option.id), option.id] : selected.filter(id => id !== option.id))} />
      {renderLabel ? <div className="min-w-0 flex-1">{renderLabel(option.label)}</div> : <span>{option.label}</span>}
    </label>)}
  </fieldset>;
}
