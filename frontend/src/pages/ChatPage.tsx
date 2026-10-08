import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import { SourceSelector } from '../components/chat/SourceSelector';
import { useAuth } from '../components/auth/AuthProvider';
import type { ChatSelection } from '../types/rag';
import { ChatComposer } from '../components/chat/ChatComposer';
import { ChatEmptyState } from '../components/chat/ChatEmptyState';
import { ChatMessage, ThinkingIndicator } from '../components/chat/ChatMessage';
import { ApiError, sendChatMessage } from '../services/api';
import type { ChatMessageData } from '../types/chat';

interface ChatOutletContext {
  newChatKey: number;
  setChatTitle: (title: string) => void;
}

function createMessage(role: ChatMessageData['role'], content: string): ChatMessageData {
  return {
    id: `${role}-${Date.now()}-${crypto.randomUUID()}`,
    role,
    content,
  };
}

export function ChatPage() {
  const { identity } = useAuth();
  const [params, setParams] = useSearchParams();
  const selectedDocument = params.get('document');
  const [selection, setSelection] = useState<ChatSelection>({ mode: 'STANDARD' });
  const { newChatKey, setChatTitle } = useOutletContext<ChatOutletContext>();
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [draft, setDraft] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const requestControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    requestControllerRef.current?.abort();
    setMessages([]);
    setDraft('');
    setIsThinking(false);
    setErrorMessage(null);
    setChatTitle('New Chat');
    setSelection({ mode: 'STANDARD' });

    return () => {
      requestControllerRef.current?.abort();
    };
  }, [newChatKey, setChatTitle, identity?.learner_id]);

  useEffect(() => {
    if (selectedDocument) setSelection({ mode: 'SOURCE_SPECIFIC', document_ids: [selectedDocument] });
  }, [selectedDocument]);

  useLayoutEffect(() => {
    const container = scrollContainerRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages, isThinking]);

  async function sendMessage() {
    const content = draft.trim();
    if (!content || isThinking) return;
    if ((selection.mode === 'SOURCE_SPECIFIC' && !selection.document_ids?.length) || (selection.mode === 'CROSS_CONTEXT' && !selection.context_ids?.length)) {
      setErrorMessage('Choose study sources before sending, or use automatic material selection.'); return;
    }

    const userMessage = createMessage('user', content);
    const conversation = [...messages, userMessage];
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setMessages(conversation);
    if (messages.length === 0) {
      const title =
        content.length > 48 ? `${content.slice(0, 45).trimEnd()}...` : content;
      setChatTitle(title);
    }
    setDraft('');
    setIsThinking(true);
    setErrorMessage(null);

    try {
      const response = await sendChatMessage(
        conversation.map(({ role, content: messageContent }) => ({
          role,
          content: messageContent,
        })),
        controller.signal,
        selection,
      );
      if (controller.signal.aborted) return;
      setMessages((current) => [
        ...current,
        { ...createMessage('assistant', response.content), sources: response.sources, citations: response.citations, retrieval_status: response.retrieval_status, retrieval_warning: response.retrieval_warning, retrieval_scope: response.retrieval_scope },
      ]);
    } catch (error) {
      if (controller.signal.aborted) return;
      setMessages((current) => current.filter((message) => message.id !== userMessage.id));
      setDraft(content);
      setErrorMessage(getChatErrorMessage(error));
      if (messages.length === 0) {
        setChatTitle('New Chat');
      }
    } finally {
      if (!controller.signal.aborted) {
        requestControllerRef.current = null;
        setIsThinking(false);
      }
    }
  }

  return (
    <section aria-label="Chat workspace" className="flex h-full min-h-0 flex-col">
      {messages.length === 0 ? (
        <ChatEmptyState onChooseSuggestion={setDraft} />
      ) : (
        <div
          aria-label="Conversation"
          className="min-h-0 flex-1 overflow-y-auto px-4 py-8 sm:px-6"
          ref={scrollContainerRef}
          role="log"
          aria-live="polite"
        >
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 pb-6">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            {isThinking && <ThinkingIndicator />}
          </div>
        </div>
      )}

      <div className="shrink-0 px-4 pb-4 pt-2 sm:px-6 sm:pb-5">
        <div className="mx-auto w-full max-w-3xl">
          <SourceSelector key={identity?.learner_id} selection={selection} disabled={isThinking} onChange={value => { setSelection(value); if (selectedDocument) setParams({}); }} />
          {errorMessage && (
            <p
              aria-live="polite"
              className="mb-3 rounded-xl border border-danger/20 bg-danger/[0.06] px-3.5 py-2.5 text-sm text-danger"
              role="alert"
            >
              {errorMessage}
            </p>
          )}
          <ChatComposer
            isThinking={isThinking}
            onChange={setDraft}
            onSubmit={sendMessage}
            value={draft}
          />
          <p className="mt-2.5 text-center text-[10px] text-subtle">
            Mentra can make mistakes. Check important information.
          </p>
        </div>
      </div>
    </section>
  );
}

function getChatErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === 'VALIDATION_ERROR' && error.details.length) return error.details[0].message;
  if (error instanceof ApiError && error.code.startsWith('RAG_')) return error.message;
  if (error instanceof ApiError && error.status === 503) {
    return 'Sorry! Mentra is currently overloaded. Please try again shortly.';
  }
  if (error instanceof ApiError && error.status === 502) {
    return 'Mentra could not respond. Please try again shortly.';
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return 'Could not reach Mentra. Check your connection and try again.';
}
