import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { ChatComposer } from '../components/chat/ChatComposer';
import { ChatEmptyState } from '../components/chat/ChatEmptyState';
import { ChatMessage, ThinkingIndicator } from '../components/chat/ChatMessage';
import {
  sampleConversations,
  sampleReply,
  type ChatMessageData,
} from './chat/mockConversations';

interface ChatOutletContext {
  activeConversationId: string | null;
  newChatKey: number;
}

function createMessage(role: ChatMessageData['role'], content: string): ChatMessageData {
  return {
    id: `${role}-${Date.now()}-${crypto.randomUUID()}`,
    role,
    content,
  };
}

export function ChatPage() {
  const { activeConversationId, newChatKey } = useOutletContext<ChatOutletContext>();
  const selectedConversation = sampleConversations.find(
    (conversation) => conversation.id === activeConversationId,
  );
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [draft, setDraft] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pendingReplyRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setMessages(selectedConversation?.messages ?? []);
    setDraft('');
    setIsThinking(false);
    if (pendingReplyRef.current) clearTimeout(pendingReplyRef.current);

    return () => {
      if (pendingReplyRef.current) clearTimeout(pendingReplyRef.current);
    };
  }, [activeConversationId, newChatKey]);

  useLayoutEffect(() => {
    const container = scrollContainerRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages, isThinking]);

  function sendMessage() {
    const content = draft.trim();
    if (!content || isThinking) return;

    setMessages((current) => [...current, createMessage('user', content)]);
    setDraft('');
    setIsThinking(true);

    pendingReplyRef.current = setTimeout(() => {
      setMessages((current) => [...current, createMessage('assistant', sampleReply)]);
      setIsThinking(false);
      pendingReplyRef.current = null;
    }, 900);
  }

  return (
    <section aria-label="Chat workspace" className="flex h-full min-h-0 flex-col">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-white/[0.06] px-4 sm:px-6">
        <div className="min-w-0">
          <h1 className="truncate text-[13px] font-medium text-slate-300">
            {selectedConversation?.title ?? 'New conversation'}
          </h1>
        </div>
        <span className="ml-3 shrink-0 rounded-full border border-white/[0.07] px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-slate-500">
          Preview
        </span>
      </div>

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
            {isThinking && <ThinkingIndicator label="Preparing a sample reply" />}
          </div>
        </div>
      )}

      <div className="shrink-0 px-4 pb-4 pt-2 sm:px-6 sm:pb-5">
        <div className="mx-auto w-full max-w-3xl">
          <ChatComposer
            isThinking={isThinking}
            onChange={setDraft}
            onSubmit={sendMessage}
            value={draft}
          />
          <p className="mt-2.5 text-center text-[10px] text-slate-600">
            Mentra preview · sample replies only, no AI connection yet
          </p>
        </div>
      </div>
    </section>
  );
}
