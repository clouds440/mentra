import { Button } from '../ui/Button';
import type { UserMemory } from '../../types/memories';

type MemoryAction = (memory: UserMemory) => void;
export function MemoryList({ items, busy, editing, onEvidence, onEdit, onConfirm, onResolve, onPin, onDelete }: {
  items: UserMemory[]; busy: boolean; editing: boolean;
  onEvidence: MemoryAction; onEdit: MemoryAction; onConfirm: MemoryAction;
  onResolve: MemoryAction; onPin: MemoryAction; onDelete: MemoryAction;
}) {
  return (
    <ul className="divide-y divide-border border-y border-border">{items.map(item => <li key={item.id} className="py-5"><p className="whitespace-pre-wrap break-words text-sm leading-6 text-body">{item.content}</p><p className="mt-2 text-xs text-muted">{item.category} · {item.status === 'active' ? 'Saved' : item.status === 'pending' ? 'Needs confirmation' : 'Conflict — review required'}{item.stale ? ' · Needs freshness review' : ''}{item.pinned ? ' · Pinned' : ''}</p><div className="mt-3 flex flex-wrap gap-1"><Button variant="ghost" size="sm" onClick={() => onEvidence(item)}>Evidence</Button><Button variant="ghost" size="sm" disabled={busy || editing} onClick={() => onEdit(item)}>Edit</Button>{(item.status === 'pending' || item.status === 'active' && item.stale) && <Button size="sm" variant="secondary" disabled={busy} onClick={() => onConfirm(item)}>Confirm current</Button>}{item.status === 'conflict' && <Button variant="secondary" size="sm" disabled={busy} onClick={() => onResolve(item)}>Review conflict</Button>}<Button variant="ghost" size="sm" disabled={busy} onClick={() => onPin(item)}>{item.pinned ? 'Unpin' : 'Pin'}</Button><Button variant="ghost" size="sm" disabled={busy} onClick={() => onDelete(item)}>Delete</Button></div></li>)}</ul>
  );
}
