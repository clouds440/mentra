import { Archive } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router';
import { useAuth } from '../auth/AuthProvider';
import { PageSection } from '../workspace/PageShell';
import { WorkspaceEmpty } from '../workspace/WorkspaceHeader';
import { Button, Skeleton } from '../ui';
import { archivedChats } from '../../services/conversations';
import { chatStore, useChatList } from '../../stores/chatStore';
import type { ChatAction, Conversation } from '../../types/conversations';
import { BulkDeleteConfirmation, ChatSelectionBar, ConversationRow } from './ChatCollection';
import { usePageRefresh } from '../../hooks/usePageRefresh';

export function ArchivedChatsSettings() {
  const { identity } = useAuth();
  return <ArchiveList key={identity?.learner_id} />;
}

function ArchiveList() {
  const { startNewChat } = useOutletContext<{ startNewChat: () => void }>();
  const view = useChatList();
  const [items, setItems] = useState<Conversation[]>([]), [next, setNext] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null), [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [selecting, setSelecting] = useState(false), [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState<Conversation[] | null>(null);
  usePageRefresh(() => setReload(value => value + 1), !loading);
  useEffect(() => { setCursor(null); setSelected(new Set()); }, [view.managementVersion]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    void archivedChats(cursor, controller.signal).then(page => {
      if (controller.signal.aborted) return;
      setItems(previous => cursor ? [...previous.filter(item => !page.items.some(row => row.id === item.id)), ...page.items] : page.items);
      setNext(page.next_cursor);
    }).catch(() => { if (!controller.signal.aborted) setError('Could not load archived chats. Try again.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [cursor, reload, view.managementVersion]);
  const rows = items.map(chat => ({ ...chat, pending_action: chatStore.pendingAction(chat.id) || chat.pending_action }));
  const picked = rows.filter(chat => selected.has(chat.id) && !chat.pending_action);
  function cancel() { setSelecting(false); setSelected(new Set()); }
  function act(chats: Conversation[], action: ChatAction) {
    if (!chatStore.bulk(chats, action)) return;
    setDeleting(null); cancel(); startNewChat();
  }
  return <PageSection title="Archived chats" description="Out of your sidebar, kept for later. Open a chat to read it, or unarchive it to bring it back." onKeyDown={event => {
    if (selecting && event.key === 'Escape' && !document.querySelector('dialog[open]')) { event.preventDefault(); cancel(); }
  }} actions={<Button variant="ghost" size="sm" onClick={() => { setCursor(null); setReload(value => value + 1); }}>Refresh</Button>}>
    {selecting && <ChatSelectionBar count={picked.length} archiveAction="unarchive" onCancel={cancel} onSelectAll={() => setSelected(new Set(rows.filter(chat => !chat.pending_action).slice(0, 100).map(chat => chat.id)))} onArchive={() => act(picked, 'unarchive')} onDelete={() => setDeleting(picked)} />}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {loading && !items.length && <Skeleton variant="list" />}
    {!loading && !error && !items.length && <WorkspaceEmpty title="No archived chats" description="Archive a chat from its menu to keep it here without deleting its messages." icon={Archive} />}
    <div className="archived-chat-list">{rows.map(chat => <ConversationRow key={chat.id} chat={chat} selecting={selecting} selected={selected.has(chat.id)} onSelect={() => { setSelecting(true); setSelected(new Set([chat.id])); }} onToggle={() => setSelected(previous => { const value = new Set(previous); if (value.has(chat.id)) value.delete(chat.id); else if (value.size < 100) value.add(chat.id); return value; })}
      onOpen={() => {}} onNewChat={startNewChat} onArchive={action => {
        if (action === 'unarchive') return chatStore.organize(chat, { archived: false }); else act([chat], action);
      }} />)}</div>
    {next && <Button variant="secondary" size="sm" disabled={loading} loading={loading} onClick={() => setCursor(next)}>Load more archived chats</Button>}
    {deleting && <BulkDeleteConfirmation chats={deleting} onCancel={() => setDeleting(null)} onConfirm={() => act(deleting, 'delete')} />}
  </PageSection>;
}
