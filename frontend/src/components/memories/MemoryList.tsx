import { Button } from '../ui/Button';
import { Check, Flag, Info, Pencil, Pin, PinOff, Sparkles, Trash2 } from 'lucide-react';
import type { UserMemory } from '../../types/memories';

type MemoryAction = (memory: UserMemory) => void;
export function MemoryList({ items, busy, editing, onEvidence, onEdit, onConfirm, onResolve, onPin, onDelete }: {
  items: UserMemory[]; busy: boolean; editing: boolean;
  onEvidence: MemoryAction; onEdit: MemoryAction; onConfirm: MemoryAction;
  onResolve: MemoryAction; onPin: MemoryAction; onDelete: MemoryAction;
}) {
  return (
    <ul aria-label="Saved memories" className="grid gap-3 md:grid-cols-2">{items.map(item => <li key={item.id} className="flex min-w-0 flex-col rounded-panel border border-border-strong bg-surface p-4 shadow-panel sm:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium capitalize text-muted"><Sparkles size={14} aria-hidden="true" />{item.category}</span>
        <div className="flex flex-wrap items-center gap-2">
          {item.pinned && <span className="inline-flex items-center gap-1 text-xs text-accent"><Pin size={12} aria-hidden="true" />Pinned</span>}
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium ${item.status === 'active' && !item.stale ? 'bg-hover text-muted' : 'bg-active text-accent'}`}>
            {item.status === 'active' && !item.stale && <Check size={12} aria-hidden="true" />}
            {item.status === 'conflict' ? 'Review conflict' : item.status === 'pending' ? 'Needs confirmation' : item.stale ? 'Needs freshness review' : 'Saved'}
          </span>
        </div>
      </div>
      <p className="flex-1 whitespace-pre-wrap break-words text-[15px] font-medium leading-7 text-heading">{item.content}</p>
      <div className="mt-5 flex flex-wrap gap-2 border-t border-border pt-4">
        <Button variant="secondary" size="sm" onClick={() => onEvidence(item)}><Info size={14} aria-hidden="true" />Evidence</Button>
        <Button variant="secondary" size="sm" disabled={busy || editing} onClick={() => onEdit(item)}><Pencil size={14} aria-hidden="true" />Edit</Button>
        <Button variant="secondary" size="sm" aria-pressed={item.pinned} disabled={busy} onClick={() => onPin(item)}>{item.pinned ? <PinOff size={14} aria-hidden="true" /> : <Pin size={14} aria-hidden="true" />}{item.pinned ? 'Unpin' : 'Pin'}</Button>
        <Button variant="danger" size="sm" disabled={busy} onClick={() => onDelete(item)}><Trash2 size={14} aria-hidden="true" />Delete</Button>
        {(item.status === 'pending' || item.status === 'active' && item.stale) && <Button size="sm" disabled={busy} onClick={() => onConfirm(item)}><Check size={14} aria-hidden="true" />Confirm current</Button>}
        {item.status === 'conflict' && <Button size="sm" disabled={busy} onClick={() => onResolve(item)}><Flag size={14} aria-hidden="true" />Review conflict</Button>}
      </div>
    </li>)}</ul>
  );
}
