import { useChatScroll } from '../hooks/useChatScroll';
﻿import { Skeleton } from '../components/ui/Skeleton';
import { ApiError } from '../services/api';
import { FileText, X } from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../components/auth/AuthProvider';
import type { ChatSelection } from '../types/rag';
import { ChatComposer } from '../components/chat/ChatComposer';
import { ChatEmptyState } from '../components/chat/ChatEmptyState';
import { ChatMessage } from '../components/chat/ChatMessage';
import { ChatActivity } from '../components/chat/ChatActivity';
import { chatStore, useChatList, useConversation } from '../stores/chatStore';
import { Spinner } from '../components/ui';
import { uploadChatAttachment, removeChatAttachment, type ChatAttachment } from '../services/chatAttachments';

interface ChatOutletContext { newChatKey: number }
interface StagedFile { id: string; file: File; preview?: string; saved?: ChatAttachment }

export function ChatPage() {
  const { identity } = useAuth();
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const selectedDocument = params.get('document');
  const practice = params.get('practice');
  const { newChatKey } = useOutletContext<ChatOutletContext>();
  const [draftId, setDraftId] = useState(() => crypto.randomUUID());
  const id = conversationId ?? draftId;
  useLayoutEffect(() => { if (!conversationId) chatStore.markDraft(id); }, [id, conversationId]);
  const view = useConversation(id);
  const list = useChatList();
  const conversation = list.items.find(chat => chat.id === id);
  const [selection, setSelection] = useState<ChatSelection>({ mode: 'STANDARD' });
  const selectionTurn = useRef<{ key: string; chat: string; turn?: string; state?: string }>();
  const [draft, setDraft] = useState('');
  useEffect(() => { if (practice) setDraft(`Help me practice ${practice.slice(0, 200)}. Ask one question at a time.`); }, [practice]);
  const [validation, setValidation] = useState<string | null>(null);
  const [files, setFiles] = useState<StagedFile[]>([]);
  const staged = useRef<StagedFile[]>([]);
  const sending = useRef(false);
  const [uploading, setUploading] = useState(false);
  const [stopping, setStopping] = useState(false);
  const uploadController = useRef(new AbortController());
  useEffect(() => {
    uploadController.current = new AbortController(); setFiles([]); staged.current = []; setUploading(false); sending.current = false;
    return () => {
      uploadController.current.abort();
      staged.current.forEach(item => { if (item.preview) URL.revokeObjectURL(item.preview); });
    };
  }, [id, identity?.learner_id]);

  function attach(selected: File[]) {
    if (sending.current || view.busy) return;
    const isImage = (file: File) => file.type.startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(file.name);
    if (selected.length + staged.current.length > 4) { setValidation('Attach up to four files per message, including at most three images.'); return; }
    if (selected.filter(isImage).length + staged.current.filter(item => isImage(item.file)).length > 3) { setValidation('Attach up to three images per message.'); return; }
    if (selected.some(file => !file.size || file.size > 25 * 1024 * 1024)) { setValidation('Choose nonempty files of at most 25 MiB each.'); return; }
    staged.current = [...staged.current, ...selected.map(file => ({ id: crypto.randomUUID(), file,
      preview: isImage(file) ? URL.createObjectURL(file) : undefined }))];
    setFiles([...staged.current]); setValidation(null);
  }
  function removeStaged(identifier: string) {
    if (sending.current) return;
    const item = staged.current.find(file => file.id === identifier);
    if (item?.preview) URL.revokeObjectURL(item.preview);
    if (item?.saved) void removeChatAttachment(item.saved.id).catch(() => {});
    staged.current = staged.current.filter(file => file.id !== identifier);
    setFiles([...staged.current]);
  }
  const scroll = useChatScroll(id, view.messages, view.loading, view.busy, chatStore.hasPending(id));
  const knownMessages = useRef<{ id: string; sequence: number | null }>({ id, sequence: null });
  const [revealing, setRevealing] = useState<Set<string>>(new Set());
  // Reset before the new workspace becomes interactive, so the first keystroke
  // cannot be erased by a deferred navigation/account effect.
  useLayoutEffect(() => { setDraftId(crypto.randomUUID()); setDraft(''); setValidation(null); setSelection({ mode: 'STANDARD' }); }, [newChatKey, identity?.learner_id]);
  useLayoutEffect(() => {
    setDraft(''); setValidation(null); setStopping(false);
    if (conversationId) void chatStore.open(conversationId, true);
    else setSelection({ mode: 'STANDARD' });
  }, [conversationId]);
  useEffect(() => {
    if (view.loading) return;
    const turn = view.turn;
    const key = `${id}:${turn?.id}:${turn?.attempt}:${turn?.state}`;
    if (selectionTurn.current?.key === key) return;
    const previous = selectionTurn.current;
    selectionTurn.current = { key, chat: id, turn: turn?.id, state: turn?.state };
    const completed = turn?.state === 'SUCCEEDED' && previous?.chat === id && (previous.turn !== turn.id || previous.state !== 'SUCCEEDED');
    if (turn?.state === 'RUNNING' || turn?.state === 'FAILED') setSelection(turn.selection);
    else setSelection(!completed && selectedDocument ? { mode: 'SOURCE_SPECIFIC', document_ids: [selectedDocument] } : { mode: 'STANDARD' });
    if (completed && selectedDocument) setParams(current => {
      const next = new URLSearchParams(current); next.delete('document'); return next;
    }, { replace: true });
  }, [id, view.loading, view.turn?.id, view.turn?.attempt, view.turn?.state]);
  useEffect(() => {
    if (selectedDocument) setSelection({ mode: 'SOURCE_SPECIFIC', document_ids: [selectedDocument] });
  }, [selectedDocument, newChatKey]);

  useLayoutEffect(() => {
    if (knownMessages.current.id !== id) {
      knownMessages.current = { id, sequence: null }; setRevealing(new Set());
    }
    if (view.loading || !view.messages.length) return;
    const previous = knownMessages.current.sequence;
    const answers = previous === null || view.loading ? [] : view.messages.filter(message => message.role === 'assistant' && message.sequence > previous);
    if (!view.loading) knownMessages.current.sequence = Math.max(previous ?? 0, ...view.messages.map(message => message.sequence));
    if (answers.length) setRevealing(current => new Set([...current, ...answers.map(message => message.id)]));
  }, [id, view.messages, view.busy, view.loading]);

  async function sendMessage() {
    const content = draft.trim() || (files.length ? 'Please help me understand the attached files.' : ''); if (!content || view.busy || sending.current || view.loading) return;
    if ((selection.mode === 'SOURCE_SPECIFIC' && !selection.document_ids?.length) || (selection.mode === 'CROSS_CONTEXT' && !selection.context_ids?.length)) {
      setValidation('Choose study sources before sending, or use automatic material selection.'); return;
    }
    const signal = uploadController.current.signal;
    sending.current = true; setUploading(true); setValidation(null);
    try {
      const saved: ChatAttachment[] = [];
      for (const item of staged.current) {
        item.saved ??= await uploadChatAttachment(item.file, signal);
        if (signal.aborted) return;
        saved.push(item.saved);
      }
      if (signal.aborted) return;
      setDraft(''); scroll.anchorNextSend();
      staged.current.forEach(item => { if (item.preview) URL.revokeObjectURL(item.preview); });
      staged.current = []; setFiles([]);
      const request = chatStore.send(id, content, selection, false, saved);
      if (!conversationId) navigate(`/chat/${id}`, { replace: true });
      await request;
    } catch (error) {
      if (!signal.aborted) setValidation(error instanceof ApiError ? error.message : 'Could not upload this file. Your message is still staged; try again.');
    } finally {
      if (!signal.aborted) { sending.current = false; setUploading(false); }
    }
  }

  return (
    <section aria-label="Chat workspace" className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      {view.loading && !view.messages.length ? (
        <div className="min-h-0 flex-1 overflow-hidden"><Skeleton variant="chat" /></div>
      ) : view.messages.length === 0 ? <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain"><ChatEmptyState onChooseSuggestion={setDraft} /></div> : (
        <div aria-label="Conversation" className="min-h-0 flex-1 overflow-y-auto overscroll-contain [overflow-anchor:none] px-4 pb-4 pt-16 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent sm:px-6 lg:pt-8"
          ref={scroll.container} role="log" aria-live="polite" tabIndex={0}
          onWheel={scroll.noteUserScroll}
          onTouchMove={scroll.noteUserScroll}
          onPointerDown={event => { if (event.target === event.currentTarget) scroll.noteUserScroll(); }}
          onKeyDown={event => { if (['ArrowUp','ArrowDown','PageUp','PageDown','Home','End','Tab',' '].includes(event.key)) scroll.noteUserScroll(); }}
          onScroll={scroll.onScroll}>
          <div className="mx-auto flex min-h-[var(--chat-content-height,0px)] w-full max-w-[52rem] flex-col">
            <div className="flex flex-col gap-8">
            {view.before !== null && <button type="button" disabled={view.loading} className="self-center rounded-lg border border-border px-4 py-2 text-xs text-muted hover:bg-hover"
              onClick={() => { const done = scroll.preparePrepend(); void chatStore.older(id).finally(done); }}>
              {view.loading ? <Spinner className="h-4 w-4" /> : 'Load earlier messages'}
            </button>}
            {scroll.groups.map((group, index) => <div key={group.key} data-user-sequence={group.userSequence}
              data-latest-turn={scroll.anchor !== null && group.userSequence === scroll.anchor || undefined} ref={scroll.anchor !== null && group.userSequence === scroll.anchor ? scroll.latest : undefined}
              className={`flex flex-col gap-8 ${scroll.anchor !== null && group.userSequence === scroll.anchor ? 'min-h-[var(--latest-turn-height,0px)]' : ''}`}>
              {group.messages.map(message => <ChatMessage key={message.id} message={message} reveal={revealing.has(message.id)} />)}
              {view.busy && index === scroll.groups.length - 1 && <ChatActivity key={`${id}-${view.turn?.id}-${view.turn?.attempt}`} conversationId={id} turnId={view.turn?.id} attempt={view.turn?.attempt} />}
            </div>)}
            {view.olderWindow && <button type="button" className="self-center rounded-lg border border-border px-4 py-2 text-xs text-muted hover:bg-hover"
              onClick={() => { scroll.showLatest(); void chatStore.open(id, true); }}>Back to latest messages</button>}
            </div>
            <p data-chat-footer className="mt-auto shrink-0 pt-6 text-center text-[10px] leading-4 text-subtle" aria-label="Chat disclaimer">Mentra can make mistakes. Check important information.</p>
          </div>
        </div>
      )}
      <div className="shrink-0 px-4 pb-4 pt-2 sm:px-6 sm:pb-5">
        <div className="mx-auto w-full max-w-[52rem]">
          {(validation || view.error || view.unsent) && <div className="mb-3 rounded-xl border border-danger/20 bg-danger/[0.06] px-3.5 py-2.5 text-sm text-danger" role="alert">
            <p>{validation || view.error || 'Your question was not sent.'}</p>
            {view.unsent && <button type="button" className="mt-2 font-medium underline underline-offset-4" onClick={() => { setDraft(view.unsent!); chatStore.clearUnsent(id); }}>Restore question</button>}
            {view.turn?.state === 'FAILED' && view.turn.error !== 'Response stopped.' && <button type="button" className="mt-2 font-medium underline underline-offset-4" onClick={() => void chatStore.send(id, '', selection, true)}>Retry response</button>}
            {!view.turn && view.error && <button type="button" className="mt-2 font-medium underline underline-offset-4" onClick={() => void chatStore.open(id, true)}>Check saved conversation</button>}
            {!view.turn && view.error && chatStore.hasPending(id) && <button type="button" className="ml-3 mt-2 font-medium underline underline-offset-4" onClick={() => void chatStore.send(id, '', selection, true)}>Retry sending</button>}
          </div>}
          <ChatComposer key={`${identity?.learner_id}-${id}`} selection={selection} onSelectionChange={value => { setSelection(value); if (selectedDocument) setParams({}); }} isThinking={view.busy || view.loading || uploading} canStop={view.busy && view.turn?.state === 'RUNNING'} stopping={stopping} onStop={() => { setStopping(true); void chatStore.stopResponse(id).finally(() => setStopping(false)); }} onChange={setDraft} onSubmit={() => void sendMessage()} value={draft} onFiles={attach} hasAttachments={!!files.length}
            attachments={<>
              {!!files.length && <ul className="flex max-h-32 items-start gap-2 overflow-y-auto px-2.5 pb-2 pt-1" aria-label="Attached files">{files.map(item => <li key={item.id} className="relative min-h-6 min-w-6 shrink-0 overflow-hidden rounded-lg border border-border bg-background text-xs text-muted" title={item.file.name}>
                {item.preview ? <img src={item.preview} alt={`Preview of ${item.file.name}`} className="block h-auto max-h-24 w-auto max-w-32" />
                  : <div className="flex h-16 w-32 items-center gap-2 px-2.5 pr-7"><FileText className="h-5 w-5 shrink-0" aria-hidden="true" /><span className="line-clamp-2 break-all">{item.file.name}</span></div>}
                <button type="button" disabled={uploading} className="absolute right-0.5 top-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-surface text-foreground shadow-sm hover:bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-50" aria-label={`Remove ${item.file.name}`} onClick={() => removeStaged(item.id)}><X size={12} aria-hidden="true" /></button>
              </li>)}</ul>}
            </>} />
        </div>
      </div>
    </section>
  );
}
