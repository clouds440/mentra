import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { Button, Select } from '../ui';
import { FormField } from '../ui/FormField';
import type { ProfileDetails } from '../../types/studentProfile';
import { preferences, depths, participationOptions, visualOptions, purposeOptions } from './options';

type PreferenceKey = 'learning_preference' | 'explanation_depth' | 'participation' | 'visual_support' | 'learning_purpose';
type Details = Pick<ProfileDetails, PreferenceKey>;
const controls = [
  { key: 'learning_purpose', label: 'Learning purpose', options: purposeOptions, fallback: 'general' },
  { key: 'learning_preference', label: 'Teaching approach', options: preferences, fallback: 'balanced' },
  { key: 'participation', label: 'Participation', options: participationOptions, fallback: 'adaptive' },
  { key: 'explanation_depth', label: 'Explanation detail', options: depths, fallback: 'standard' },
  { key: 'visual_support', label: 'Visual support', options: visualOptions, fallback: 'adaptive' },
] as const;

export function TeachingPreferences({ details, onChange, errors }: {
  details: Details;
  onChange: (key: PreferenceKey, value: Details[PreferenceKey]) => void;
  errors: Record<string, string>;
}) {
  return <fieldset className="space-y-4">
    <legend className="text-sm font-medium text-heading">Learning preferences</legend>
    <p className="text-xs leading-5 text-muted">These are defaults. Your current question and instructions always come first.</p>
    <div className="grid gap-5 sm:grid-cols-2">
      {controls.map(control => <FormField key={control.key} id={control.key} label={control.label} error={errors[control.key]}
        hint={control.options.find(option => option.value === (details[control.key] ?? control.fallback))?.description}>
        {props => <Select {...props} name={control.key} value={details[control.key] ?? control.fallback}
          onChange={event => onChange(control.key, event.target.value as Details[typeof control.key])}>
          {control.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </Select>}
      </FormField>)}
    </div>
    <PreferencePreview key={controls.map(control => details[control.key]).join(':')} details={details} />
  </fieldset>;
}

function PreferencePreview({ details }: { details: Details }) {
  const [answer, setAnswer] = useState<number>();
  const approach = details.learning_preference;
  const text = approach === 'examples_first' ? 'Put 3 into a doubling function and you get 6. A function applies the same rule to each input.'
    : approach === 'conceptual' ? 'A function connects each input to one output through a rule. Doubling means each output is twice its input.'
    : 'A doubling function multiplies its input by 2. For example, an input of 3 gives an output of 6.';
  return <section aria-label="Preference preview" className="rounded-panel border border-border bg-surface p-4">
    <h3 className="text-sm font-medium text-heading">Preview your preferences</h3>
    <p className="mt-1 text-xs leading-5 text-subtle">Example: a doubling function. This local illustration is not an AI response or an assessment.</p>
    <div className="mt-3 space-y-3 text-sm leading-6 text-body">
      {approach === 'step_by_step' ? <ol className="list-decimal space-y-1 pl-5"><li>Start with an input: 3.</li><li>Multiply it by 2.</li><li>The output is 6.</li></ol> : <p>{text}</p>}
      {details.explanation_depth !== 'brief' && <p>The rule stays the same even when the input changes: 4 becomes 8.</p>}
      {details.explanation_depth === 'deep' && <p>We can write the relationship as f(x) = 2x. Here x is the input and f(x) is the output. Different functions use different rules; a function assigns one output to each allowed input.</p>}
      {details.visual_support === 'prefer_visuals' && <div role="img" aria-label="Input 3, multiply by 2, output 6" className="flex flex-wrap items-center gap-2 text-xs text-heading">{['Input: 3', 'Multiply by 2', 'Output: 6'].map((label, index) => <span className="inline-flex items-center gap-2" key={label}>{index > 0 && <ArrowRight size={14} aria-hidden="true" />}<span className="rounded-control border border-border bg-card px-2 py-1">{label}</span></span>)}</div>}
      {details.participation === 'interactive' && <div className="rounded-control border border-border bg-card p-3">
        <p className="text-sm text-heading">Your turn: what is the output when the input is 5?</p>
        <div className="mt-2 flex flex-wrap gap-2">{[8, 10, 12].map(value => <Button type="button" size="sm" variant={answer === value ? 'primary' : 'secondary'} aria-pressed={answer === value} key={value} onClick={() => setAnswer(value)}>{value}</Button>)}</div>
        {answer !== undefined && <p role="status" className="mt-2 text-xs text-muted">{answer === 10 ? 'Yes: 5 × 2 = 10.' : 'Try multiplying the input, 5, by 2.'} This preview is not recorded.</p>}
      </div>}
      {details.learning_purpose !== 'general' && <p className="text-xs text-muted">{purposeOptions.find(option => option.value === details.learning_purpose)?.description}</p>}
    </div>
    <p className="mt-3 text-xs leading-5 text-subtle">Real replies adapt to your question. Interactive activities and visuals appear when useful, not in every answer.</p>
  </section>;
}
