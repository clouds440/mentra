import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import mentraLogo from '../../assets/mentra-logo.png';
import type { ChatMessageData } from '../../types/chat';

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
          className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center"
        >
          <img alt="" className="h-6 w-6 object-contain" src={mentraLogo} />
        </div>
      )}
      <div
        className={
          isAssistant
            ? 'min-w-0 max-w-full flex-1 text-[14px] leading-7 text-body'
              : 'max-w-[88%] whitespace-pre-wrap rounded-2xl border border-border bg-message px-4 py-3 text-[14px] leading-6 text-foreground sm:max-w-[78%]'
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

export function ThinkingIndicator({ label = '' }: ThinkingIndicatorProps) {
  return (
    <div aria-live="polite" className="flex items-center gap-3.5 text-sm text-subtle">
      <span className="grid h-7 w-7 place-items-center">
        <img alt="" aria-hidden="true" className="h-6 w-6 object-contain" src={mentraLogo} />
      </span>
      <span className="flex items-center gap-2">
        {label}
        <span aria-hidden="true" className="flex gap-1">
          <i className="h-1 w-1 animate-pulse rounded-full bg-subtle" />
          <i className="h-1 w-1 animate-pulse rounded-full bg-subtle [animation-delay:150ms]" />
          <i className="h-1 w-1 animate-pulse rounded-full bg-subtle [animation-delay:300ms]" />
        </span>
      </span>
    </div>
  );
}
