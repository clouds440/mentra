import { type RefObject } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Popover } from './Popover';

type ActionMenuItem = { id: string; label: string; icon: LucideIcon; destructive?: boolean }
  & ({ onSelect: () => void; disabled?: boolean; href?: never } | { href: string; onSelect?: never; disabled?: never });
/** Add actions through data; shared placement, dismissal and keyboard behavior. */
export function ActionMenu({ anchor, open, onClose, id, label, items, placement, align, className }: {
  anchor: RefObject<HTMLElement | null>; open: boolean; onClose: () => void; id: string; label: string; items: ActionMenuItem[];
  placement?: 'above' | 'below'; align?: 'start' | 'end'; className?: string;
}) {
  return <Popover anchor={anchor} open={open} onClose={onClose} id={id} role="menu" label={label} width={176} placement={placement} align={align} className={className} focusOnOpen>
    <div onKeyDown={event => {
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role=menuitem]:not(:disabled)'));
      if (!buttons.length) return;
      const current = buttons.indexOf(document.activeElement as HTMLElement);
      const index = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length;
      buttons[index].focus();
    }}>{items.map(item => {
      const { id: key, label: title, icon: Icon, destructive } = item;
      const styles = `flex min-h-10 w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-xs transition-colors duration-150 hover:bg-hover focus-visible:bg-hover focus-visible:outline-none disabled:opacity-50 ${destructive ? 'text-danger' : 'text-heading'}`;
      const content = <><Icon size={14} aria-hidden />{title}</>;
      const dismiss = () => { onClose(); anchor.current?.focus({ preventScroll: true }); };
      return item.href
        ? <a key={key} role="menuitem" href={item.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer"
            className={styles} onClick={dismiss} onAuxClick={event => { if (event.button === 1) dismiss(); }}>{content}</a>
        : <button key={key} type="button" role="menuitem" disabled={item.disabled} className={styles}
            onClick={() => { dismiss(); item.onSelect?.(); }}>{content}</button>;
    })}</div>
  </Popover>;
}
