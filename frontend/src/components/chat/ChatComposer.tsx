import { ArrowUp, Paperclip, Mic, Square, LoaderCircle, BookOpenText } from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ClipboardEvent, KeyboardEvent, ReactNode } from 'react';
import { SourceSelector, type SourcePickerHandle } from './SourceSelector';
import type { ChatSelection } from '../../types/rag';
import { Button, Textarea } from '../ui';
import { useVoiceInput } from './useVoiceInput';
import { VoiceInput } from './VoiceInput';
import { useAssessmentEvaluation } from '../../stores/assessmentSession';

interface ChatComposerProps {
  materialPickerRequest?: number;
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
  materialPickerRequest,
}: ChatComposerProps) {
  const evaluation = useAssessmentEvaluation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const previousPickerRequest = useRef(materialPickerRequest);
  useEffect(() => {
    if (previousPickerRequest.current !== materialPickerRequest) {
      previousPickerRequest.current = materialPickerRequest;
      setPickerOpen(true);
    }
  }, [materialPickerRequest]);
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
  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const resize = () => {
      textarea.style.height = '0px';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 192)}px`;
    };
    resize();
    let width = textarea.clientWidth;
    const observer = new ResizeObserver(() => {
      if (textarea.clientWidth === width) return;
      width = textarea.clientWidth;
      resize();
    });
    observer.observe(textarea);
    return () => observer.disconnect();
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (pickerRef.current?.handleKeyDown(event)) return;
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!voice.busy) onSubmit();
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLFormElement>) {
    // Files and items describe the same clipboard payload; use one collection
    // so screenshots aren't staged twice. Text-only paste remains native.
    const files = Array.from(event.clipboardData.files);
    if (!files.length) for (const item of Array.from(event.clipboardData.items)) {
      if (item.kind !== 'file') continue;
      const file = item.getAsFile();
      if (file) files.push(file);
    }
    if (!files.length) return;
    event.preventDefault();
    if (isThinking) return;
    onFiles(files);
    requestAnimationFrame(() => textareaRef.current?.focus());
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
      className="chat-composer rounded-panel border border-border-strong bg-card p-1.5 shadow-panel focus-within:border-border-hover"
      onPaste={handlePaste}
      onSubmit={(event) => {
        event.preventDefault();
        if (!voice.busy) onSubmit();
      }}
    >
      {attachments}
      {(evaluation.evaluating > 0 || evaluation.submitting > 0) && <div role="status" aria-label="Quiz evaluation" aria-live="polite" className="flex items-center gap-2 px-2.5 py-2 text-xs text-muted">
        <LoaderCircle size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
        <span>{evaluation.evaluating > 0 ? 'Evaluating quiz answers…' : 'Submitting quiz answers…'}</span>
      </div>}
      <div className={`composer-entry ${voice.busy ? 'composer-voice-active' : ''}`}>
      <Textarea
        dir="auto"
        hidden={voice.busy}
        aria-label="Ask Mentra anything"
        aria-haspopup="listbox"
        aria-expanded={pickerOpen}
        aria-controls={pickerOpen ? 'study-material-results' : undefined}
        aria-activedescendant={pickerOpen ? activeOptionId : undefined}
        aria-autocomplete="list"
        className="max-h-[min(12rem,30dvh)] min-h-11 resize-none overflow-y-auto border-0 bg-transparent px-2.5 py-2 text-base leading-6 placeholder:text-subtle sm:text-sm focus-visible:border-0 focus-visible:ring-0 disabled:opacity-60"
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
      <div className="composer-voice"><VoiceInput voice={voice} /></div>
      <div className="composer-toolbar flex items-center justify-between px-1 pb-0.5 pt-0">
        <input ref={fileRef} type="file" multiple className="hidden" aria-label="Upload chat files" disabled={isThinking}
          onChange={event => { onFiles(Array.from(event.target.files ?? [])); event.target.value = ''; requestAnimationFrame(() => textareaRef.current?.focus()); }} />
        <div className="flex items-center gap-0.5"><button
          type="button"
          disabled={isThinking}
          onClick={() => fileRef.current?.click()}
          aria-label="Attach files to chat"
          className="composer-attach inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-xs text-subtle transition-colors duration-150 enabled:hover:text-foreground focus-visible:text-foreground"
          title="Read files in chat; choose later whether to add them to Library"
        >
          <Paperclip aria-hidden="true" size={16} />
          <span className="hidden sm:inline">Attach files</span>
        </button>
        <button type="button" disabled={isThinking} aria-label="Choose study material" title="Choose study material"
          onClick={() => { setQuery(''); setPickerOpen(value => !value); }}
          className="inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-xs text-subtle transition-colors duration-150 enabled:hover:text-foreground focus-visible:text-foreground">
          <BookOpenText size={16} aria-hidden="true" /><span className="hidden sm:inline">Study material</span>
        </button></div>
        <div className="composer-actions flex items-center gap-3">
          <span className="hidden text-[11px] text-subtle sm:inline">
            Enter to send · Shift + Enter for a new line
          </span>
          <Button
            aria-label={voice.phase === 'recording' ? 'Stop recording' : 'Record voice message'}
            title={voice.phase === 'recording' ? 'Stop recording' : 'Record voice message'}
            className="composer-mic icon-control h-8 min-h-8 w-8 rounded-control p-0"
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
            className="composer-send icon-control h-8 min-h-8 w-8 rounded-control p-0"
            disabled={canStop ? stopping : (!value.trim() && !hasAttachments) || isThinking || voice.busy}
            size="sm"
            type={canStop ? 'button' : 'submit'}
            onClick={canStop ? onStop : undefined}
          >
            {canStop ? <Square aria-hidden="true" size={15} fill="currentColor" /> : <ArrowUp aria-hidden="true" size={17} strokeWidth={2.2} />}
          </Button>
        </div>
      </div>
      </div>
    </form>
    </>
  );
}
