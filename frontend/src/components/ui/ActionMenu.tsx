import { type RefObject } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Popover } from './Popover';

export interface ActionMenuItem { id: string; label: string; icon: LucideIcon; onSelect: () => void; destructive?: boolean; disabled?: boolean }
/** Add actions through data; shared placement, dismissal and keyboard behavior. */
export function ActionMenu({ anchor, open, onClose, id, label, items }: {
  anchor: RefObject<HTMLElement>; open: boolean; onClose: () => void; id: string; label: string; items: ActionMenuItem[];
}) {
  return <Popover anchor={anchor} open={open} onClose={onClose} id={id} role="menu" label={label} width={176} focusOnOpen>
    <div onKeyDown={event => {
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role=menuitem]:not(:disabled)'));
      if (!buttons.length) return;
      const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const index = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length;
      buttons[index].focus();
    }}>{items.map(({id: key, label: title, icon: Icon, onSelect, destructive, disabled}) => <button key={key} type="button" role="menuitem" disabled={disabled}
      className={`flex min-h-10 w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-xs transition-colors duration-150 hover:bg-hover focus-visible:bg-hover focus-visible:outline-none disabled:opacity-50 ${destructive ? 'text-danger' : 'text-heading'}`}
      onClick={() => { onClose(); anchor.current?.focus(); onSelect(); }}><Icon size={14} aria-hidden />{title}</button>)}</div>
  </Popover>;
}
