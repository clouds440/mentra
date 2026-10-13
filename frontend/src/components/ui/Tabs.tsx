import { useRef } from 'react';

export interface TabOption<T extends string> { value: T; label: string; id: string; panel: string; disabled?: boolean }
export function Tabs<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: TabOption<T>[]; onChange: (value: T) => void }) {
  const root = useRef<HTMLDivElement>(null);
  return <div ref={root} role="tablist" aria-label={label} className="workspace-tabs" onKeyDown={event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const enabled = options.filter(option => !option.disabled);
    if (!enabled.length) return;
    const current = enabled.findIndex(option => option.id === (event.target as HTMLElement).id);
    if (current < 0) return;
    event.preventDefault();
    const next = event.key === 'Home' ? enabled[0] : event.key === 'End' ? enabled[enabled.length - 1] : enabled[(current + (event.key === 'ArrowRight' ? 1 : enabled.length - 1)) % enabled.length];
    onChange(next.value);
    root.current?.querySelector<HTMLButtonElement>(`[id="${CSS.escape(next.id)}"]`)?.focus();
  }}>{options.map(option => <button key={option.value} type="button" role="tab" id={option.id} aria-controls={option.panel} aria-selected={value === option.value} tabIndex={value === option.value ? 0 : -1} disabled={option.disabled} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>;
}
