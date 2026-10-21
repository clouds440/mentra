import { ActionMenu } from '../ui/ActionMenu';
import { useLongPress } from '../../hooks/useLongPress';
import { buttonStyles } from '../ui/Button';
import { Skeleton } from '../ui/Skeleton';
import { Spinner } from '../ui/Spinner';
import { Check, Pencil, Trash2, X, MoreVertical } from 'lucide-react';
import { useId, useRef, useState } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router-dom';
import { chatStore, useChatList } from '../../stores/chatStore';
import type { Conversation } from '../../types/conversations';
import { cn } from '../../utils/cn';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { ChatSearch } from './ChatSearch';

function ConversationRow({ chat, onOpen }: { chat: Conversation; onOpen: () => void }) {
  const [editing, setEditing] = useState(false), [deleting, setDeleting] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuAnchor = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const longPress = useLongPress(() => setMenuOpen(true));
  const [title, setTitle] = useState(chat.title);
  const [deleteBusy, setDeleteBusy] = useState(false), [deleteError, setDeleteError] = useState('');
  const deletePending = useRef(false);
  const dialogId = useId();
  const { conversationId } = useParams(); const navigate = useNavigate();
  const deleteConversation = async () => {
    if (deletePending.current) return;
    deletePending.current = true; setDeleteBusy(true); setDeleteError('');
    try {
      if (await chatStore.remove(chat.id)) {
        setDeleting(false);
        if (conversationId === chat.id) navigate('/');
      } else setDeleteError('Could not delete this chat. Please try again.');
    } catch {
      setDeleteError('Could not delete this chat. Please try again.');
    } finally {
      deletePending.current = false; setDeleteBusy(false);
    }
  };
  const control = 'history-action grid h-7 w-7 shrink-0 place-items-center rounded-md text-subtle hover:bg-hover hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent';
  const rowControls = 'opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto group-focus-within:opacity-100 group-focus-within:pointer-events-auto motion-safe:transition-opacity';
  return <div className="group my-1 rounded-lg">
    {editing ? <form className="flex items-center gap-1 px-2 py-1" onSubmit={event => { event.preventDefault(); void chatStore.rename(chat.id, title); setEditing(false); }}>
      <Input autoFocus aria-label="Conversation title" value={title} onChange={event => setTitle(event.target.value)} maxLength={120} required
        className="min-w-0 flex-1 rounded border border-border bg-background p-1.5 text-xs text-foreground" />
      <button type="submit" aria-label="Save conversation title" className={control}><Check size={14} /></button>
      <button type="button" aria-label="Cancel rename" className={control} onClick={() => setEditing(false)}><X size={14} /></button>
    </form> : <div className="relative min-w-0">
      <NavLink to={`/chat/${chat.id}`} {...longPress} onClick={onOpen} title={chat.title} className={({ isActive }) => cn('block w-full min-w-0 truncate rounded-lg select-none pl-3 pr-10 py-2 [-webkit-touch-callout:none] text-xs text-muted group-hover:bg-hover group-focus-within:bg-hover hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent', isActive && 'bg-active font-medium text-foreground')}>
        {chat.title}
      </NavLink>
      <div className={cn('absolute right-1 top-1/2 -translate-y-1/2', !menuOpen && rowControls)}>
        <button ref={menuAnchor} type="button" aria-label={`Actions for ${chat.title}`} aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuOpen ? menuId : undefined}
          className={control} onClick={() => setMenuOpen(value => !value)} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); setMenuOpen(true); } }}><MoreVertical size={15} aria-hidden="true" /></button>
      </div>
      <ActionMenu anchor={menuAnchor} open={menuOpen} onClose={() => setMenuOpen(false)} id={menuId} label={`Actions for ${chat.title}`} items={[
        {id:'rename', label:'Rename', icon:Pencil, onSelect:() => { setTitle(chat.title); setEditing(true); setDeleting(false); }},
        {id:'delete', label:'Delete', icon:Trash2, destructive:true, onSelect:() => { setDeleteError(''); setDeleting(true); }},
      ]} />
    </div>}
    {deleting && <Dialog open busy={deleteBusy} onDismiss={() => setDeleting(false)} aria-labelledby={`${dialogId}-title`} aria-describedby={`${dialogId}-description`} className="max-w-sm">
      <div className="flex items-center gap-2 text-heading"><Trash2 size={17} className="shrink-0 text-danger" aria-hidden="true" /><h2 id={`${dialogId}-title`} className="text-sm font-semibold">Delete chat?</h2></div>
      <p id={`${dialogId}-description`} className="mt-3 break-words text-sm leading-6 text-muted">“{chat.title}” and its messages will be permanently deleted. This cannot be undone.</p>
      {deleteError && <p role="alert" className="mt-3 text-xs text-danger">{deleteError}</p>}
      <div className="mt-5 flex justify-end gap-2">
        <Button autoFocus size="sm" variant="secondary" disabled={deleteBusy} onClick={() => setDeleting(false)}>Cancel</Button>
        <Button size="sm" variant="danger" loading={deleteBusy} onClick={() => void deleteConversation()}>Delete chat</Button>
      </div>
    </Dialog>}
  </div>;
}

export function ConversationList({ onOpen }: { onOpen: () => void }) {
  const view = useChatList();
  return <section aria-label="Conversation history" className="mt-6 min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-2">
    <div className="mb-1 flex items-center justify-between gap-2 pl-3"><h2 className="text-[11px] font-medium uppercase tracking-[0.12em] text-subtle">Recent chats</h2><ChatSearch onOpen={onOpen} /></div>
    {view.items.map(chat => <ConversationRow key={chat.id} chat={chat} onOpen={onOpen} />)}
    {!view.items.length && (view.loading ? <Skeleton variant="list" rows={5} className="px-3 py-3" /> : <p className="px-3 py-3 text-xs leading-5 text-subtle">Your conversations will appear here.</p>)}
    {view.error && <div className="px-3 py-2 text-xs text-danger" role="alert"><p>{view.error}</p><button type="button" className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'mt-1' })} onClick={() => void chatStore.sync()}>Try again</button></div>}
    {view.more && <button type="button" disabled={view.loading} className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'mx-3 my-3' })} onClick={() => void chatStore.more()}>{view.loading ? <Spinner className="h-4 w-4" /> : 'Load more chats'}</button>}
  </section>;
}
