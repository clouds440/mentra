import { Select } from '../ui';
import type { AssessmentAssistance } from '../../types/assessments';

export function AssistanceSelector({value, onChange, disabled, label = 'Assistance used'}: {
  value: AssessmentAssistance; onChange: (value: AssessmentAssistance) => void; disabled?: boolean; label?: string;
}) {
  return <label className="block space-y-1.5 text-xs text-muted">
    <span>Did you use AI or hints?</span>
    <Select aria-label={label} disabled={disabled} value={value} onChange={event => onChange(event.target.value as AssessmentAssistance)}>
      <option value="unknown">Assistance not specified</option>
      <option value="independent">I answered independently</option>
      <option value="assisted">I used AI or hints</option>
    </Select>
    <span className="block leading-5">Self-reported AI or hint use applies a 0.9× final-score adjustment. Question correctness is unchanged.</span>
  </label>;
}
