import { ArrowUp, Paperclip } from 'lucide-react';
import { useLayoutEffect, useRef } from 'react';
import type { KeyboardEvent } from 'react';
import { Button, Textarea } from '../ui';

interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isThinking: boolean;
  onFiles: (files: File[]) => void;
  hasAttachments?: boolean;
}

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  isThinking,
  onFiles,
  hasAttachments,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 192)}px`;
  }, [value]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form
      aria-label="Message Mentra"
      className="rounded-2xl border border-border-strong bg-surface p-2 shadow-lg shadow-shadow/10 focus-within:border-border-hover"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <Textarea
        aria-label="Ask Mentra anything"
        className="max-h-48 min-h-[3.25rem] resize-none overflow-y-auto border-0 bg-transparent px-2.5 py-2 text-sm leading-6 placeholder:text-subtle focus-visible:border-0 focus-visible:ring-0 disabled:opacity-60"
        disabled={isThinking}
        onChange={(event) => onChange(event.currentTarget.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask Mentra anything..."
        ref={textareaRef}
        rows={1}
        value={value}
      />
      <div className="flex items-center justify-between px-1 pb-0.5 pt-1">
        <input ref={fileRef} type="file" multiple className="hidden" aria-label="Upload chat files" disabled={isThinking}
          onChange={event => { onFiles(Array.from(event.target.files ?? [])); event.target.value = ''; }} />
        <button
          type="button"
          disabled={isThinking}
          onClick={() => fileRef.current?.click()}
          aria-label="Attach files to chat"
          className="inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-xs text-subtle"
          title="Read files in chat; choose later whether to add them to Library"
        >
          <Paperclip aria-hidden="true" size={16} />
          <span className="hidden sm:inline">Attach files</span>
        </button>
        <div className="flex items-center gap-3">
          <span className="hidden text-[11px] text-subtle sm:inline">
            Enter to send · Shift + Enter for a new line
          </span>
          <Button
            aria-label="Send message"
            className="h-9 min-h-9 w-9 rounded-xl p-0"
            disabled={(!value.trim() && !hasAttachments) || isThinking}
            size="sm"
            type="submit"
          >
            <ArrowUp aria-hidden="true" size={17} strokeWidth={2.2} />
          </Button>
        </div>
      </div>
    </form>
  );
}
