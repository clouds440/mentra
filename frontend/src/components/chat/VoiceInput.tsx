import { LoaderCircle, X } from 'lucide-react';
import type { useVoiceInput } from './useVoiceInput';

export function VoiceInput({ voice }: { voice: ReturnType<typeof useVoiceInput> }) {
  const { phase } = voice;
  if (!voice.busy && !voice.error) return null;
  return <>
    {voice.busy && <div className="flex min-h-[3.25rem] items-center gap-3 px-2.5 py-2" aria-label="Voice recording">
      <button type="button" onClick={voice.cancel} aria-label="Cancel voice input"
        className="icon-control flex h-8 w-8 shrink-0 items-center justify-center rounded-control text-muted hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"><X size={17} aria-hidden="true" /></button>
      {phase === 'recording' ? <>
        <span aria-hidden="true" className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-danger motion-reduce:animate-none" />
        <div aria-hidden="true" className="flex h-8 min-w-0 flex-1 items-center justify-center gap-1.5">
          {voice.levels.map((level, index) => <span key={index} className="h-[30px] w-1 flex-1 max-w-2 rounded-full bg-primary/80 transition-transform duration-100 motion-reduce:transition-none"
            style={{ transform: `scaleY(${.1 + level * .9})` }} />)}
        </div>
        <span role="status" className="sr-only">Recording</span>
        <span className="shrink-0 font-mono text-xs tabular-nums text-muted">0:{String(voice.seconds).padStart(2, '0')}</span>
      </> : <span role="status" className="flex flex-1 items-center gap-2 text-sm text-muted">
        <LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
        {phase === 'permission' ? 'Waiting for microphone…' : 'Transcribing…'}
      </span>}
    </div>}
    {voice.error && <p role="alert" className="px-2.5 py-2 text-xs text-danger">{voice.error}
      {voice.canRetry && <><button type="button" onClick={voice.retry} className="ml-2 underline">Retry</button>
        <button type="button" onClick={voice.cancel} className="ml-2 underline">Dismiss</button></>}</p>}
  </>;
}
