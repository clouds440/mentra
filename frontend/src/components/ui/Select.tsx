import { Children, isValidElement, useId, useLayoutEffect, useRef, useState, type ReactNode, type SelectHTMLAttributes } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '../../utils/cn';
import { Popover } from './Popover';

type Option = { value: string; label: string; disabled: boolean; group?: string };
function text(node: ReactNode): string { return Children.toArray(node).map(child => isValidElement<{ children?: ReactNode }>(child) ? text(child.props.children) : String(child)).join(''); }
function options(children: ReactNode, group?: string): Option[] {
  return Children.toArray(children).flatMap(child => {
    if (!isValidElement<{ value?: string | number; children?: ReactNode; disabled?: boolean; label?: string }>(child)) return [];
    if (child.type === 'option') return [{ value: String(child.props.value ?? text(child.props.children)), label: child.props.label ?? text(child.props.children), disabled: !!child.props.disabled, group }];
    return options(child.props.children, child.type === 'optgroup' ? child.props.label : group);
  });
}

/** Custom listbox with native form values and the existing change-event contract. */
export function Select({ className, children, value, defaultValue, multiple, disabled, id, onChange, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  const generated = useId(); const controlId = id ?? generated; const listId = `${controlId}-options`;
  const trigger = useRef<HTMLButtonElement>(null); const native = useRef<HTMLSelectElement>(null);
  const [local, setLocal] = useState(defaultValue); const current = value ?? local;
  const items = options(children);
  const selected = (Array.isArray(current) ? current : [current ?? items[0]?.value ?? '']).map(String);
  const [open, setOpen] = useState(false); const [active, setActive] = useState(0); const [label, setLabel] = useState('');
  const typeahead = useRef({ value: '', at: 0 });
  useLayoutEffect(() => {
    const parent = trigger.current?.closest('label') ?? (id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null);
    if (parent) { const copy = parent.cloneNode(true) as HTMLElement; copy.querySelectorAll('[data-select-control]').forEach(node => node.remove()); setLabel(copy.textContent?.trim() ?? ''); }
  }, [id, children]);
  useLayoutEffect(() => { if (disabled || trigger.current?.matches(':disabled')) setOpen(false); }, [disabled]);
  useLayoutEffect(() => {
    if (!open) return;
    // Scroll only the listbox after its portal has been positioned. Native
    // scrollIntoView can scroll the underlying onboarding page on short screens.
    const frame = requestAnimationFrame(() => {
      const panel = document.getElementById(listId);
      const option = document.getElementById(`${listId}-${active}`);
      if (!panel || !option) return;
      const bounds = panel.getBoundingClientRect(); const row = option.getBoundingClientRect();
      if (row.top < bounds.top + 6) panel.scrollTop -= bounds.top + 6 - row.top;
      else if (row.bottom > bounds.bottom - 6) panel.scrollTop += row.bottom - bounds.bottom + 6;
    });
    return () => cancelAnimationFrame(frame);
  }, [open, active, listId]);
  const enabled = items.map((item, index) => item.disabled ? -1 : index).filter(index => index >= 0);
  function show() { const selectedIndex = items.findIndex(item => selected.includes(item.value) && !item.disabled); setActive(selectedIndex >= 0 ? selectedIndex : enabled[0] ?? 0); setOpen(true); }
  function choose(index: number) {
    const item = items[index]; if (!item || item.disabled || !native.current) return;
    const next = multiple ? selected.includes(item.value) ? selected.filter(entry => entry !== item.value) : [...selected, item.value] : [item.value];
    for (const option of native.current.options) option.selected = next.includes(option.value);
    setLocal(multiple ? next : next[0]);
    native.current.dispatchEvent(new Event('change', { bubbles: true }));
    if (!multiple) setOpen(false); trigger.current?.focus();
  }
  const name = props['aria-label'] ?? label;
  const display = items.filter(item => selected.includes(item.value)).map(item => item.label).join(', ') || 'Select an option';
  return <span data-select-control className={cn('inline-block w-full align-middle', className)}>
    <button ref={trigger} id={controlId} type="button" role="combobox" aria-label={name || undefined} aria-labelledby={props['aria-labelledby']}
      aria-describedby={props['aria-describedby']} aria-invalid={props['aria-invalid']} aria-required={props.required} aria-haspopup="listbox"
      aria-controls={open ? listId : undefined} aria-expanded={open} aria-activedescendant={open ? `${listId}-${active}` : undefined}
      disabled={disabled} className="field-control flex w-full items-center justify-between gap-3 text-left text-sm"
      onClick={() => open ? setOpen(false) : show()} onBlur={event => { if (!event.relatedTarget || !document.getElementById(listId)?.contains(event.relatedTarget as Node)) setOpen(false); }}
      onKeyDown={event => {
        if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
          event.preventDefault(); if (!open) { show(); return; }
          const position = enabled.indexOf(active);
          setActive(event.key === 'Home' ? enabled[0] : event.key === 'End' ? enabled[enabled.length-1] : enabled[(position + (event.key === 'ArrowDown' ? 1 : -1) + enabled.length) % enabled.length] ?? 0);
        } else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (open) choose(active); else show(); }
        else if (event.key === 'Escape') { event.preventDefault(); setOpen(false); }
        else if (event.key === 'Tab') setOpen(false);
        else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          const now = Date.now(); typeahead.current = { value: now - typeahead.current.at > 700 ? event.key.toLowerCase() : typeahead.current.value + event.key.toLowerCase(), at: now };
          const match = items.findIndex(item => !item.disabled && item.label.toLowerCase().startsWith(typeahead.current.value));
          if (match >= 0) { if (!open) show(); setActive(match); }
        }
      }}><span className="min-w-0 truncate">{display}</span><ChevronDown size={16} aria-hidden="true" className={cn('shrink-0 text-subtle transition-transform', open && 'rotate-180')} /></button>
    <select {...props} ref={native} hidden aria-hidden="true" aria-label={undefined} aria-labelledby={undefined} tabIndex={-1} disabled={disabled} multiple={multiple} value={current} onChange={onChange}
      onInvalid={event => { event.preventDefault(); trigger.current?.focus(); }}>{children}</select>
    <Popover anchor={trigger} open={open} onClose={() => setOpen(false)} id={listId} role="listbox" label={name ? `${name} options` : 'Options'} multiselectable={multiple} matchWidth>
      {items.length === 0 && <p className="px-3 py-3 text-sm text-muted">No options available</p>}
      {items.map((item, index) => <div key={`${item.value}-${index}`}>
        {item.group && item.group !== items[index-1]?.group && <p className="px-3 py-2 text-xs font-medium text-subtle">{item.group}</p>}
        <div id={`${listId}-${index}`} role="option" aria-selected={selected.includes(item.value)} aria-disabled={item.disabled || undefined} data-value={item.value}
          onPointerDown={event => event.preventDefault()} onMouseEnter={() => !item.disabled && setActive(index)} onClick={() => choose(index)}
          className={cn('flex min-h-10 cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm', item.disabled ? 'cursor-not-allowed text-subtle opacity-50' : index === active ? 'bg-active text-heading' : 'text-body hover:bg-hover', selected.includes(item.value) && 'font-medium text-accent')}>
          <span className="min-w-0 flex-1 break-words">{item.label}</span>{selected.includes(item.value) && <Check size={16} aria-hidden="true" className="shrink-0" />}
        </div>
      </div>)}
    </Popover>
  </span>;
}
