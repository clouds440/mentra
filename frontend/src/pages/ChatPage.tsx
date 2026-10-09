import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import { SourceSelector } from '../components/chat/SourceSelector';
import { useAuth } from '../components/auth/AuthProvider';
import type { ChatSelection } from '../types/rag';
import { ChatComposer } from '../components/chat/ChatComposer';
import { ChatEmptyState } from '../components/chat/ChatEmptyState';
import { ChatMessage } from '../components/chat/ChatMessage';
import { ChatActivity } from '../components/chat/ChatActivity';
import { chatStore, useChatList, useConversation } from '../stores/chatStore';
import { Spinner } from '../components/ui';
import { uploadChatAttachment, removeChatAttachment, type ChatAttachment } from '../services/chatAttachments';

interface ChatOutletContext { newChatKey: number; setChatTitle: (title: string) => void }

export function ChatPage() {
  const { identity } = useAuth();
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const selectedDocument = params.get('document');
  const practice = params.get('practice');
  const { newChatKey, setChatTitle } = useOutletContext<ChatOutletContext>();
  const [draftId, setDraftId] = useState(() => crypto.randomUUID());
  const id = conversationId ?? draftId;
  const view = useConversation(id);
  const list = useChatList();
  const conversation = list.items.find(chat => chat.id === id);
  const [selection, setSelection] = useState<ChatSelection>({ mode: 'STANDARD' });
  const [draft, setDraft] = useState('');
  useEffect(() => { if (practice) setDraft(`Help me practice ${practice.slice(0, 200)}. Ask one question at a time.`); }, [practice]);
  const [validation, setValidation] = useState<string | null>(null);
  const [files, setFiles] = useState<ChatAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const uploadController = useRef(new AbortController());
  useEffect(() => {
    uploadController.current = new AbortController(); setFiles([]); setUploading(false);
    return () => uploadController.current.abort();
  }, [id, identity?.learner_id]);

  async function attach(selected: File[]) {
    if (uploading || view.busy) return;
    if (selected.length + files.length > 4) { setValidation('Attach up to four files per message.'); return; }
    const signal = uploadController.current.signal;
    setUploading(true); setValidation(null);
    try {
      for (const file of selected) {
        const saved = await uploadChatAttachment(file, signal);
        if (signal.aborted) return;
        setFiles(previous => [...previous, saved]);
      }
    } catch (error) { if (!signal.aborted) setValidation(error instanceof Error ? error.message : 'Could not upload this file.'); }
    finally { if (!signal.aborted) setUploading(false); }
  }
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const prependRef = useRef<number | null>(null);
  const bottomRef = useRef(true);

  // Reset before the new workspace becomes interactive, so the first keystroke
  // cannot be erased by a deferred navigation/account effect.
  useLayoutEffect(() => { setDraftId(crypto.randomUUID()); setDraft(''); setValidation(null); setSelection({ mode: 'STANDARD' }); }, [newChatKey, identity?.learner_id]);
  useLayoutEffect(() => {
    setDraft(''); setValidation(null); bottomRef.current = true;
    if (conversationId) void chatStore.open(conversationId);
    else setSelection({ mode: 'STANDARD' });
  }, [conversationId]);
  useEffect(() => { if (conversation) setSelection(conversation.selection); }, [conversation?.id, conversation?.revision]);
  useEffect(() => {
    if (selectedDocument) setSelection({ mode: 'SOURCE_SPECIFIC', document_ids: [selectedDocument] });
  }, [selectedDocument, newChatKey]);
  useEffect(() => { setChatTitle(conversation?.title ?? 'New Chat'); }, [conversation?.title, setChatTitle, id]);

  useLayoutEffect(() => {
    const container = scrollContainerRef.current; if (!container) return;
    if (prependRef.current !== null) { container.scrollTop += container.scrollHeight - prependRef.current; prependRef.current = null; }
    else if (bottomRef.current) container.scrollTop = container.scrollHeight;
  }, [view.messages, view.busy]);

  function sendMessage() {
    const content = draft.trim() || (files.length ? 'Please read the attached files.' : ''); if (!content || view.busy || uploading) return;
    if ((selection.mode === 'SOURCE_SPECIFIC' && !selection.document_ids?.length) || (selection.mode === 'CROSS_CONTEXT' && !selection.context_ids?.length)) {
      setValidation('Choose study sources before sending, or use automatic material selection.'); return;
    }
    setDraft(''); setValidation(null); bottomRef.current = true;
    void chatStore.send(id, content, selection, false, files); setFiles([]);
    if (!conversationId) navigate(`/chat/${id}`, { replace: true });
  }

  return (
    <section aria-label="Chat workspace" className="flex h-full min-h-0 flex-col">
      {view.loading && !view.messages.length ? (
        <div className="grid flex-1 place-items-center" role="status" aria-label="Loading conversation"><Spinner /></div>
      ) : view.messages.length === 0 ? <ChatEmptyState onChooseSuggestion={setDraft} /> : (
        <div aria-label="Conversation" className="min-h-0 flex-1 overflow-y-auto px-4 py-8 sm:px-6"
          ref={scrollContainerRef} role="log" aria-live="polite"
          onScroll={() => { const el = scrollContainerRef.current; if (el) bottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }}>
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 pb-6">
            {view.before !== null && <button type="button" disabled={view.loading} className="self-center rounded-lg border border-border px-4 py-2 text-xs text-muted hover:bg-hover"
              onClick={() => { prependRef.current = scrollContainerRef.current?.scrollHeight ?? null; bottomRef.current = false; void chatStore.older(id); }}>
              {view.loading ? 'Loading earlier messages…' : 'Load earlier messages'}
            </button>}
            {view.messages.map(message => <ChatMessage key={message.id} message={message} />)}
            {view.busy && <ChatActivity key={`${id}-${view.turn?.id}-${view.turn?.attempt}`} conversationId={id} turnId={view.turn?.id} attempt={view.turn?.attempt} />}
            {view.olderWindow && <button type="button" className="self-center rounded-lg border border-border px-4 py-2 text-xs text-muted hover:bg-hover"
              onClick={() => { bottomRef.current = true; void chatStore.open(id, true); }}>Back to latest messages</button>}
          </div>
        </div>
      )}
      <div className="shrink-0 px-4 pb-4 pt-2 sm:px-6 sm:pb-5">
        <div className="mx-auto w-full max-w-3xl">
          <SourceSelector key={`${identity?.learner_id}-${id}`} selection={selection} disabled={view.busy} onChange={value => { setSelection(value); if (selectedDocument) setParams({}); }} />
          {(validation || view.error || view.unsent) && <div className="mb-3 rounded-xl border border-danger/20 bg-danger/[0.06] px-3.5 py-2.5 text-sm text-danger" role="alert">
            <p>{validation || view.error || 'Your question was not sent.'}</p>
            {view.unsent && <button type="button" className="mt-2 font-medium underline underline-offset-4" onClick={() => { setDraft(view.unsent!); chatStore.clearUnsent(id); }}>Restore question</button>}
            {view.turn?.state === 'FAILED' && <button type="button" className="mt-2 font-medium underline underline-offset-4" onClick={() => void chatStore.send(id, '', selection, true)}>Retry response</button>}
            {!view.turn && view.error && <button type="button" className="mt-2 font-medium underline underline-offset-4" onClick={() => void chatStore.open(id, true)}>Check saved conversation</button>}
            {!view.turn && view.error && chatStore.hasPending(id) && <button type="button" className="ml-3 mt-2 font-medium underline underline-offset-4" onClick={() => void chatStore.send(id, '', selection, true)}>Retry sending</button>}
          </div>}
          {!!files.length && <ul className="mb-2 flex flex-wrap gap-2" aria-label="Attached files">{files.map(file => <li key={file.id} className="rounded-lg border border-border px-3 py-2 text-xs text-muted">
            {file.filename} <button type="button" className="ml-2 underline" aria-label={`Remove ${file.filename}`} onClick={() => {
              setFiles(previous => previous.filter(value => value.id !== file.id)); void removeChatAttachment(file.id).catch(() => {});
            }}>Remove</button>
          </li>)}</ul>}
          {uploading && <p role="status" className="mb-2 text-xs text-muted">Uploading files…</p>}
          <ChatComposer isThinking={view.busy || view.loading || uploading} onChange={setDraft} onSubmit={sendMessage} value={draft} onFiles={selected => void attach(selected)} hasAttachments={!!files.length} />
          <p className="mt-2.5 text-center text-[10px] text-subtle">Mentra can make mistakes. Check important information.</p>
        </div>
      </div>
    </section>
  );
}
