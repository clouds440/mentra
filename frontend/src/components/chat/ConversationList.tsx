import { ChevronRight, Pin } from 'lucide-react';
import { useId, useLayoutEffect, useRef, useState } from 'react';
import { chatStore, useChatList } from '../../stores/chatStore';
import { ChatSearch } from './ChatSearch';
import { ChatSelectionBar, ConversationRow, BulkDeleteConfirmation } from './ChatCollection';
import { Button, Skeleton } from '../ui';
import type { ChatAction, Conversation } from '../../types/conversations';
import { cn } from '../../utils/cn';

export function ConversationList({ onOpen, onNewChat }: { onOpen: () => void; onNewChat: () => void }) {
  const view = useChatList();
  const listId = useId();
  const [expanded, setExpanded] = useState(true);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState<Conversation[] | null>(null);
  const list = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => { if (list.current) list.current.inert = !expanded; }, [expanded]);
  const chats = view.items.filter(chat => !chat.archived_at);
  const pinned = chats.filter(chat => chat.pinned_at).sort((a, b) => b.pinned_at!.localeCompare(a.pinned_at!) || b.id.localeCompare(a.id));
  const recent = chats.filter(chat => !chat.pinned_at);
  const picked = chats.filter(chat => selected.has(chat.id) && !chat.pending_action);
  function cancelSelection() { setSelecting(false); setSelected(new Set()); }
  function toggle(id: string) { setSelected(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else if (next.size < 100) next.add(id); return next; }); }
  function act(rows: Conversation[], action: ChatAction) {
    if (!chatStore.bulk(rows, action)) return;
    setDeleting(null); cancelSelection(); onNewChat(); onOpen();
  }
  function row(chat: Conversation) { return <ConversationRow key={chat.id} chat={chat} selecting={selecting} selected={selected.has(chat.id)}
    onSelect={() => { setSelecting(true); setSelected(new Set([chat.id])); setExpanded(true); }} onToggle={() => toggle(chat.id)}
    onOpen={onOpen} onNewChat={() => { onNewChat(); onOpen(); }} onArchive={action => act([chat], action)} />; }
  return <section aria-label="Conversation history" className="mt-6 flex min-h-0 flex-1 flex-col overflow-hidden px-3" onKeyDown={event => {
    if (selecting && event.key === 'Escape' && !document.querySelector('dialog[open]')) { event.preventDefault(); cancelSelection(); }
  }}>
    {selecting && <ChatSelectionBar count={picked.length} onCancel={cancelSelection} onSelectAll={() => setSelected(new Set(chats.filter(chat => !chat.pending_action).slice(0, 100).map(chat => chat.id)))} onArchive={() => act(picked, 'archive')} onDelete={() => setDeleting(picked)} />}
    <div className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain">
      {pinned.length > 0 && <section aria-label="Pinned chats" className="chat-pinned-section"><h2 className="chat-pinned-heading"><Pin size={18} strokeWidth={1.8} aria-hidden="true" />Pinned</h2>{pinned.map(row)}</section>}
      <div className="recents-header mb-1 flex shrink-0 items-center rounded-lg text-muted transition-colors">
        <h2 className="min-w-0 flex-1"><button type="button" aria-expanded={expanded} aria-controls={listId} className="recents-toggle flex h-10 w-full items-center gap-3 rounded-lg px-3 text-start text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent" onClick={() => setExpanded(value => !value)}><ChevronRight size={18} strokeWidth={1.8} aria-hidden="true" className={cn('shrink-0 motion-safe:transition-transform motion-safe:duration-150', expanded && 'rotate-90')} />Recents</button></h2>
        <ChatSearch onOpen={onOpen} />
      </div>
      <div className="recents-list-reveal" data-expanded={expanded}><div ref={list} id={listId} aria-hidden={!expanded || undefined} className="min-h-0 min-w-0">
        {recent.map(row)}
        {!recent.length && (view.loading ? <Skeleton variant="list" rows={5} className="px-3 py-3" /> : <p className="px-3 py-3 text-xs leading-5 text-subtle">Your conversations will appear here.</p>)}
        {view.error && <div className="px-3 py-2 text-xs text-danger" role="alert"><p>{view.error}</p><Button size="sm" variant="secondary" className="mt-1" onClick={() => void chatStore.sync()}>Try again</Button></div>}
        {view.more && <Button size="sm" variant="secondary" className="mx-3 my-3" disabled={view.loading} loading={view.loading} onClick={() => void chatStore.more()}>Load more chats</Button>}
      </div></div>
    </div>
    {deleting && <BulkDeleteConfirmation chats={deleting} onCancel={() => setDeleting(null)} onConfirm={() => act(deleting, 'delete')} />}
  </section>;
}
