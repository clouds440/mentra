import { Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessageData } from '../../pages/chat/mockConversations';

interface ChatMessageProps {
  message: ChatMessageData;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isAssistant = message.role === 'assistant';

  return (
    <article
      aria-label={isAssistant ? 'Mentra response' : 'Your message'}
      className={isAssistant ? 'flex gap-3.5' : 'flex justify-end'}
    >
      {isAssistant && (
        <div
          aria-hidden="true"
          className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-sky-300/15 bg-sky-300/[0.07] text-sky-200"
        >
          <Sparkles size={14} strokeWidth={1.8} />
        </div>
      )}
      <div
        className={
          isAssistant
            ? 'min-w-0 max-w-full flex-1 text-[14px] leading-7 text-slate-300'
              : 'max-w-[88%] whitespace-pre-wrap rounded-2xl border border-white/[0.07] bg-white/[0.055] px-4 py-3 text-[14px] leading-6 text-slate-100 sm:max-w-[78%]'
        }
      >
        {isAssistant ? (
          <div className="markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        ) : (
          message.content
        )}
      </div>
    </article>
  );
}

interface ThinkingIndicatorProps {
  label?: string;
}

export function ThinkingIndicator({ label = 'Mentra is thinking' }: ThinkingIndicatorProps) {
  return (
    <div aria-live="polite" className="flex items-center gap-3.5 text-sm text-slate-500">
      <span className="grid h-7 w-7 place-items-center rounded-lg border border-sky-300/15 bg-sky-300/[0.07] text-sky-200">
        <Sparkles aria-hidden="true" size={14} strokeWidth={1.8} />
      </span>
      <span className="flex items-center gap-2">
        {label}
        <span aria-hidden="true" className="flex gap-1">
          <i className="h-1 w-1 animate-pulse rounded-full bg-slate-500" />
          <i className="h-1 w-1 animate-pulse rounded-full bg-slate-500 [animation-delay:150ms]" />
          <i className="h-1 w-1 animate-pulse rounded-full bg-slate-500 [animation-delay:300ms]" />
        </span>
      </span>
    </div>
  );
}
