import type { InputFieldDefinition } from '../../types/interactions';
import { FormField, Input, Select, Textarea } from '../ui';

export function fieldError(field: InputFieldDefinition, value: string): string | undefined {
  if (!value.trim()) return field.required !== false ? 'Enter a value to continue.' : undefined;
  if (Array.from(value).length > (field.max_length ?? 300)) return `Use at most ${field.max_length ?? 300} characters.`;
  if (field.kind === 'number') {
    const number = Number(value);
    if (!Number.isFinite(number)) return 'Enter a valid number.';
    if (field.minimum != null && number < field.minimum) return `Use ${field.minimum} or higher.`;
    if (field.maximum != null && number > field.maximum) return `Use ${field.maximum} or lower.`;
  }
  if (field.kind === 'select' && !field.options?.some(option => option.id === value)) return 'Choose an available option.';
}

export function InteractionField({ field, value, onChange, disabled, autoFocus = false }: {
  field: InputFieldDefinition; value: string; onChange: (value: string) => void; disabled: boolean; autoFocus?: boolean;
}) {
  const error = value ? fieldError(field, value) : undefined;
  return <FormField label={field.label} error={disabled ? undefined : error} hint={field.required === false ? 'Optional' : undefined}>{props => {
    const common = { ...props, value, disabled, required: field.required !== false, className: 'chat-input-text', onChange: (event: { target: { value: string } }) => onChange(event.target.value) };
    if (field.kind === 'select') return <Select {...common} value={value.trim() ? value : ''}><option value="">Choose an option</option>{field.options?.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</Select>;
    if (field.kind === 'long_text') return <Textarea {...common} rows={3} placeholder={field.placeholder} autoFocus={autoFocus} />;
    return <Input {...common} type={field.kind === 'number' ? 'number' : 'text'} step="any" min={field.minimum ?? undefined} max={field.maximum ?? undefined} placeholder={field.placeholder} autoFocus={autoFocus} />;
  }}</FormField>;
}
