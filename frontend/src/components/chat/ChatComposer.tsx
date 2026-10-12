import { ArrowUp, Paperclip, Mic, Square, LoaderCircle } from 'lucide-react';
import { useLayoutEffect, useRef, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { SourceSelector, type SourcePickerHandle } from './SourceSelector';
import type { ChatSelection } from '../../types/rag';
import { Button, Textarea } from '../ui';
import { useVoiceInput } from './useVoiceInput';
import { VoiceInput } from './VoiceInput';

interface ChatComposerProps {
  selection: ChatSelection;
  onSelectionChange: (value: ChatSelection) => void;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isThinking: boolean;
  canStop?: boolean;
  stopping?: boolean;
  onStop?: () => void;
  onFiles: (files: File[]) => void;
  hasAttachments?: boolean;
  attachments?: ReactNode;
}

export function ChatComposer({
  selection,
  onSelectionChange,
  value,
  onChange,
  onSubmit,
  isThinking,
  canStop, stopping, onStop,
  onFiles,
  hasAttachments,
  attachments,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeOptionId, setActiveOptionId] = useState<string>();
  const pickerRef = useRef<SourcePickerHandle>(null);
  const dismissedMention = useRef<number | null>(null);
  const mentionRef = useRef<{ start: number; end: number } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const voice = useVoiceInput(text => {
    onChange(value + (value && !/\s$/.test(value) ? ' ' : '') + text);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, isThinking);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 192)}px`;
  }, [value]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (pickerRef.current?.handleKeyDown(event)) return;
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!voice.busy) onSubmit();
    }
  }

  function updateMention(text: string, cursor: number) {
    const match = /(?:^|\s)@([^@\n]*)$/.exec(text.slice(0, cursor));
    if (!match) {
      mentionRef.current = null; dismissedMention.current = null;
      setPickerOpen(false); setQuery(''); return;
    }
    const start = cursor - match[1].length - 1;
    mentionRef.current = { start, end: cursor };
    setQuery(match[1]);
    setPickerOpen(dismissedMention.current !== start);
  }

  function closePicker() {
    dismissedMention.current = mentionRef.current?.start ?? null;
    setPickerOpen(false);
  }

  return (
    <>
      <SourceSelector ref={pickerRef} selection={selection} onChange={onSelectionChange} disabled={isThinking}
        anchor={textareaRef} pickerOpen={pickerOpen} query={query} onActiveOptionChange={setActiveOptionId} onClose={closePicker}
        onPick={() => {
          const mention = mentionRef.current;
          if (mention) onChange(value.slice(0, mention.start) + value.slice(mention.end));
          mentionRef.current = null; dismissedMention.current = null; setPickerOpen(false); setQuery('');
          requestAnimationFrame(() => {
            textareaRef.current?.focus();
            if (mention) textareaRef.current?.setSelectionRange(mention.start, mention.start);
          });
        }} />
    <form
      aria-label="Message Mentra"
      className="rounded-2xl border border-border-strong bg-surface p-2 shadow-lg shadow-shadow/10 focus-within:border-border-hover"
      onSubmit={(event) => {
        event.preventDefault();
        if (!voice.busy) onSubmit();
      }}
    >
      {attachments}
      <Textarea
        dir="auto"
        hidden={voice.busy}
        aria-label="Ask Mentra anything"
        aria-haspopup="listbox"
        aria-expanded={pickerOpen}
        aria-controls={pickerOpen ? 'study-material-results' : undefined}
        aria-activedescendant={pickerOpen ? activeOptionId : undefined}
        aria-autocomplete="list"
        className="max-h-48 min-h-[3.25rem] resize-none overflow-y-auto border-0 bg-transparent px-2.5 py-2 text-sm leading-6 placeholder:text-subtle focus-visible:border-0 focus-visible:ring-0 disabled:opacity-60"
        disabled={isThinking}
        onChange={(event) => {
          const text = event.currentTarget.value;
          const cursor = event.currentTarget.selectionStart;
          onChange(text);
          updateMention(text, cursor);
        }}
        onSelect={event => updateMention(event.currentTarget.value, event.currentTarget.selectionStart)}
        onKeyDown={handleKeyDown}
        placeholder="Ask Mentra anything... Type @ to choose study material"
        ref={textareaRef}
        rows={1}
        value={value}
      />
      <VoiceInput voice={voice} />
      <div className="flex items-center justify-between px-1 pb-0.5 pt-1">
        <input ref={fileRef} type="file" multiple className="hidden" aria-label="Upload chat files" disabled={isThinking}
          onChange={event => { onFiles(Array.from(event.target.files ?? [])); event.target.value = ''; requestAnimationFrame(() => textareaRef.current?.focus()); }} />
        <button
          type="button"
          disabled={isThinking}
          onClick={() => fileRef.current?.click()}
          aria-label="Attach files to chat"
          className="inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-xs text-subtle transition-colors duration-150 enabled:hover:text-foreground focus-visible:text-foreground"
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
            aria-label={voice.phase === 'recording' ? 'Stop recording' : 'Record voice message'}
            title={voice.phase === 'recording' ? 'Stop recording' : 'Record voice message'}
            className="h-9 min-h-9 w-9 rounded-xl p-0"
            disabled={isThinking || voice.phase === 'permission' || voice.phase === 'processing'}
            size="sm" variant="ghost" type="button"
            onClick={() => voice.phase === 'recording' ? voice.stop() : void voice.start()}
          >
            {voice.phase === 'recording' ? <Square size={17} aria-hidden="true" />
              : voice.phase === 'processing' || voice.phase === 'permission' ? <LoaderCircle size={17} className="animate-spin" aria-hidden="true" />
              : <Mic size={17} aria-hidden="true" />}
          </Button>
          <Button
            aria-label={canStop ? 'Stop response' : 'Send message'}
            className="h-9 min-h-9 w-9 rounded-xl p-0"
            disabled={canStop ? stopping : (!value.trim() && !hasAttachments) || isThinking || voice.busy}
            size="sm"
            type={canStop ? 'button' : 'submit'}
            onClick={canStop ? onStop : undefined}
          >
            {canStop ? <Square aria-hidden="true" size={15} fill="currentColor" /> : <ArrowUp aria-hidden="true" size={17} strokeWidth={2.2} />}
          </Button>
        </div>
      </div>
    </form>
    </>
  );
}
