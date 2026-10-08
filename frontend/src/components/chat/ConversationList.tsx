import { Check, Pencil, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router-dom';
import { chatStore, useChatList } from '../../stores/chatStore';
import type { Conversation } from '../../types/conversations';
import { cn } from '../../utils/cn';

function ConversationRow({ chat, onOpen }: { chat: Conversation; onOpen: () => void }) {
  const [editing, setEditing] = useState(false), [deleting, setDeleting] = useState(false);
  const [title, setTitle] = useState(chat.title);
  const { conversationId } = useParams(); const navigate = useNavigate();
  const control = 'grid h-7 w-7 shrink-0 place-items-center rounded-md text-subtle hover:bg-hover hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent';
  return <div className="group my-1 rounded-lg">
    {editing ? <form className="flex items-center gap-1 px-2 py-1" onSubmit={event => { event.preventDefault(); void chatStore.rename(chat.id, title); setEditing(false); }}>
      <input autoFocus aria-label="Conversation title" value={title} onChange={event => setTitle(event.target.value)} maxLength={120} required
        className="min-w-0 flex-1 rounded border border-border bg-background p-1.5 text-xs text-foreground" />
      <button type="submit" aria-label="Save conversation title" className={control}><Check size={14} /></button>
      <button type="button" aria-label="Cancel rename" className={control} onClick={() => setEditing(false)}><X size={14} /></button>
    </form> : <div className="flex min-w-0 items-center gap-0.5">
      <NavLink to={`/chat/${chat.id}`} onClick={onOpen} title={chat.title} className={({ isActive }) => cn('min-w-0 flex-1 truncate rounded-lg px-3 py-2 text-xs text-muted hover:bg-hover hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent', isActive && 'bg-active font-medium text-foreground')}>
        {chat.title}
      </NavLink>
      <button type="button" aria-label={`Rename ${chat.title}`} className={control} onClick={() => { setTitle(chat.title); setEditing(true); setDeleting(false); }}><Pencil size={13} /></button>
      <button type="button" aria-label={`Delete ${chat.title}`} className={control} onClick={() => setDeleting(value => !value)}><Trash2 size={13} /></button>
    </div>}
    {deleting && <div className="mx-2 mb-2 rounded-lg border border-danger/20 bg-danger/[0.06] p-2 text-xs">
      <p className="text-muted">Delete this conversation and its messages?</p>
      <div className="mt-2 flex gap-3"><button type="button" className="text-danger" onClick={async () => { if (await chatStore.remove(chat.id) && conversationId === chat.id) navigate('/'); }}>Confirm deletion</button>
        <button type="button" className="text-muted" onClick={() => setDeleting(false)}>Cancel</button></div>
    </div>}
  </div>;
}

export function ConversationList({ onOpen }: { onOpen: () => void }) {
  const view = useChatList();
  return <section aria-label="Conversation history" className="mt-8 min-h-0 flex-1 overflow-y-auto px-3">
    <h2 className="px-3 text-[11px] font-medium uppercase tracking-[0.12em] text-subtle">Recent chats</h2>
    {view.items.map(chat => <ConversationRow key={chat.id} chat={chat} onOpen={onOpen} />)}
    {!view.items.length && <p className="px-3 py-3 text-xs leading-5 text-subtle">{view.loading ? 'Loading your conversations…' : 'Your conversations will appear here.'}</p>}
    {view.error && <div className="px-3 py-2 text-xs text-danger" role="alert"><p>{view.error}</p><button type="button" className="mt-1 underline" onClick={() => void chatStore.sync()}>Retry sync</button></div>}
    {view.more && <button type="button" disabled={view.loading} className="mx-3 my-3 text-xs text-muted hover:text-foreground" onClick={() => void chatStore.more()}>{view.loading ? 'Loading…' : 'Load more chats'}</button>}
  </section>;
}
