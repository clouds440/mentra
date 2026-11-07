import { Archive, ArchiveRestore, Check, ListChecks, MoreVertical, Pencil, Pin, PinOff, Trash2, X } from 'lucide-react';
import { useId, useRef, useState } from 'react';
import { NavLink, useParams } from 'react-router';
import { m, useReducedMotion } from '../ui/Motion';
import { ActionMenu } from '../ui/ActionMenu';
import { Button, IconButton, Input, Spinner } from '../ui';
import { Dialog } from '../ui/Dialog';
import { useLongPress } from '../../hooks/useLongPress';
import { chatStore, useChatList } from '../../stores/chatStore';
import type { ChatAction, Conversation } from '../../types/conversations';
import { cn } from '../../utils/cn';

export function ChatSelectionBar({ count, archiveAction = 'archive', onCancel, onSelectAll, onArchive, onDelete }: {
  count: number; archiveAction?: 'archive' | 'unarchive'; onCancel: () => void; onSelectAll: () => void; onArchive: () => void; onDelete: () => void;
}) {
  const reduced = useReducedMotion();
  const ArchiveIcon = archiveAction === 'archive' ? Archive : ArchiveRestore;
  return <m.div role="toolbar" aria-label="Chat selection" className="chat-selection-bar" initial={reduced ? false : { opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }}
    transition={{ type: 'spring', stiffness: 430, damping: 32 }} onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); onCancel(); } }}>
    <IconButton autoFocus size="sm" aria-label="Exit chat selection" onClick={onCancel}><X size={16} aria-hidden="true" /></IconButton>
    <span className="chat-selection-count" role="status" aria-live="polite">{count} <span className="sr-only">chats selected</span></span>
    <IconButton size="sm" aria-label="Select all chats" title="Select up to 100 available chats" onClick={onSelectAll}><ListChecks size={17} aria-hidden="true" /></IconButton>
    <IconButton size="sm" disabled={!count} aria-label={archiveAction === 'archive' ? 'Archive selected chats' : 'Unarchive selected chats'} onClick={onArchive}><ArchiveIcon size={17} aria-hidden="true" /></IconButton>
    <IconButton size="sm" disabled={!count} aria-label="Delete selected chats" className="text-danger" onClick={onDelete}><Trash2 size={16} aria-hidden="true" /></IconButton>
  </m.div>;
}

export function BulkDeleteConfirmation({ chats, onCancel, onConfirm }: { chats: Conversation[]; onCancel: () => void; onConfirm: () => void }) {
  return <Dialog open title={`Delete ${chats.length} ${chats.length === 1 ? 'chat' : 'chats'}?`} onDismiss={onCancel} className="max-w-md">
    <p className="text-sm leading-6 text-body">The selected chats and their messages will be permanently deleted. This cannot be undone.</p>
    <ul className="chat-delete-preview">{chats.slice(0, 5).map(chat => <li key={chat.id}>{chat.title}</li>)}{chats.length > 5 && <li>and {chats.length - 5} more</li>}</ul>
    <p className="mt-3 text-xs leading-5 text-muted">You can keep using Mentra while deletion finishes in the background.</p>
    <div className="mt-5 flex justify-end gap-2"><Button autoFocus variant="secondary" onClick={onCancel}>Cancel</Button><Button variant="danger" onClick={onConfirm}>Delete {chats.length} {chats.length === 1 ? 'chat' : 'chats'}</Button></div>
  </Dialog>;
}

export function ConversationRow({ chat, selecting, selected, onSelect, onToggle, onOpen, onArchive, onNewChat }: {
  chat: Conversation; selecting: boolean; selected: boolean; onSelect: () => void; onToggle: () => void;
  onOpen: () => void; onArchive: (action: ChatAction) => void | Promise<unknown>; onNewChat: () => void;
}) {
  const [editing, setEditing] = useState(false), [deleting, setDeleting] = useState(false), [menuOpen, setMenuOpen] = useState(false), [busy, setBusy] = useState(false), [deleteError, setDeleteError] = useState('');
  const [title, setTitle] = useState(chat.title);
  const menuAnchor = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const { conversationId } = useParams();
  const pending = chat.pending_action || chatStore.pendingAction(chat.id);
  const longPress = useLongPress(() => { if (!pending && !selecting) setMenuOpen(true); });
  const reduced = useReducedMotion();
  async function pin() { if (busy) return; setBusy(true); try { await chatStore.organize(chat, { pinned: !chat.pinned_at }); } finally { setBusy(false); } }
  async function archive() { if (busy) return; setBusy(true); try { await onArchive(chat.archived_at ? 'unarchive' : 'archive'); } finally { setBusy(false); } }
  async function remove() {
    if (busy) return; setBusy(true); setDeleteError('');
    try { if (await chatStore.remove(chat.id, chat)) { setDeleting(false); if (conversationId === chat.id) onNewChat(); } else setDeleteError('Could not delete this chat. Please try again.'); }
    finally { setBusy(false); }
  }
  return <m.div layout={reduced ? false : 'position'} transition={{ type: 'spring', stiffness: 460, damping: 36 }} className={cn('chat-history-row group', selected && selecting && 'is-selected', pending && 'is-pending')} data-pending-action={pending || undefined}>
    {pending ? <div className="chat-row-pending" aria-disabled="true"><span className="truncate">{chat.title}</span><Spinner className="h-3.5 w-3.5 shrink-0" aria-hidden="true" /><span className="sr-only">{pending === 'delete' ? 'Deleting' : pending === 'archive' ? 'Archiving' : 'Unarchiving'} chat</span></div>
      : selecting ? <button type="button" role="checkbox" aria-checked={selected} aria-label={`Select ${chat.title}`} className="chat-row-select" onClick={onToggle}>
        <span aria-hidden="true" className="chat-selection-circle">{selected && <Check size={13} strokeWidth={2.5} />}</span><span className="truncate">{chat.title}</span>
      </button> : editing ? <form className="flex items-center gap-1 px-2 py-1" onSubmit={event => { event.preventDefault(); void chatStore.rename(chat.id, title, chat); setEditing(false); }}>
        <Input autoFocus aria-label="Conversation title" value={title} onChange={event => setTitle(event.target.value)} maxLength={120} required className="min-w-0 flex-1 text-xs" />
        <IconButton size="sm" type="submit" aria-label="Save conversation title"><Check size={14} /></IconButton><IconButton size="sm" aria-label="Cancel rename" onClick={() => setEditing(false)}><X size={14} /></IconButton>
      </form> : <div className="relative min-w-0">
        <NavLink to={`/chat/${chat.id}`} {...longPress} onClick={onOpen} title={chat.title} className={({ isActive }) => cn('chat-row-link', isActive && 'bg-active font-medium text-foreground')}>{chat.title}</NavLink>
        <div className={cn('chat-row-actions', menuOpen && 'is-open')}><button ref={menuAnchor} type="button" aria-label={`Actions for ${chat.title}`} aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuOpen ? menuId : undefined}
          disabled={busy} className="history-action grid h-7 w-7 place-items-center rounded-md text-subtle hover:bg-hover focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setMenuOpen(value => !value)} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); setMenuOpen(true); } }}><MoreVertical size={15} aria-hidden="true" /></button></div>
        <ActionMenu anchor={menuAnchor} open={menuOpen} onClose={() => setMenuOpen(false)} id={menuId} label={`Actions for ${chat.title}`} items={[
          { id: 'select', label: 'Select', icon: ListChecks, onSelect },
          ...(!chat.archived_at ? [{ id: 'pin', label: chat.pinned_at ? 'Unpin' : 'Pin', icon: chat.pinned_at ? PinOff : Pin, onSelect: () => { void pin(); } }] : []),
          { id: 'archive', label: chat.archived_at ? 'Unarchive' : 'Archive', icon: chat.archived_at ? ArchiveRestore : Archive, onSelect: () => { void archive(); } },
          { id: 'rename', label: 'Rename', icon: Pencil, onSelect: () => { setTitle(chat.title); setEditing(true); } },
          { id: 'delete', label: 'Delete', icon: Trash2, destructive: true, onSelect: () => { setDeleteError(''); setDeleting(true); } },
        ]} />
      </div>}
    {deleting && <Dialog open title="Delete chat?" busy={busy} onDismiss={() => setDeleting(false)} className="max-w-sm">
      <p className="text-sm leading-6 text-muted">“{chat.title}” and its messages will be permanently deleted. This cannot be undone.</p>{deleteError && <p role="alert" className="mt-3 text-xs text-danger">{deleteError}</p>}
      <div className="mt-5 flex justify-end gap-2"><Button autoFocus size="sm" variant="secondary" disabled={busy} onClick={() => setDeleting(false)}>Cancel</Button><Button size="sm" variant="danger" loading={busy} onClick={() => void remove()}>Delete chat</Button></div>
    </Dialog>}
  </m.div>;
}

export function ChatActionFeedback({ error, notice }: { error: string | null; notice: string | null }) {
  if (!error && !notice) return null;
  return <div className={cn('chat-action-feedback', error && 'text-danger')} role={error ? 'alert' : 'status'}><p>{error || notice}</p><IconButton size="sm" aria-label="Dismiss chat action message" onClick={() => chatStore.clearManagementFeedback()}><X size={13} aria-hidden="true" /></IconButton></div>;
}

export function ChatManagementFeedback() {
  const view = useChatList();
  return view.actionError || view.notice ? <div className="chat-management-toast"><ChatActionFeedback error={view.actionError} notice={view.notice} /></div> : null;
}
