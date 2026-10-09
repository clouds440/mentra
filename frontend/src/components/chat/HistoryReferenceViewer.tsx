import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { memoryApi } from '../../services/memories';
import type { HistoryReference, MemoryReference, HistoryWindow, UserMemory } from '../../types/memories';
import { Button } from '../ui/Button';
import { MemoryDetails } from '../memories/MemoryDetails';
import { MarkdownContent } from '../content/MarkdownContent';
import { Spinner } from '../ui/Spinner';

export function HistoryReferenceViewer({ reference, onClose }: { reference: HistoryReference | MemoryReference; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [history, setHistory] = useState<HistoryWindow>();
  const [memory, setMemory] = useState<UserMemory>();
  const [error, setError] = useState('');
  useEffect(() => {
    dialog.current?.showModal();
    const controller = new AbortController();
    if ('memory_id' in reference) {
      memoryApi.detail(reference.memory_id, controller.signal).then(setMemory).catch(cause => { if (!controller.signal.aborted) setError(cause.message); });
    } else {
      memoryApi.history(reference.conversation_id, reference.sequence, controller.signal).then(setHistory).catch(cause => { if (!controller.signal.aborted) setError(cause.message); });
    }
    return () => controller.abort();
  }, [reference]);
  return <dialog ref={dialog} onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) onClose(); }} aria-labelledby="history-reference-title" className="m-auto max-h-[85dvh] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto rounded-2xl border border-border bg-popover p-5 text-foreground shadow-xl">
    <div className="mb-5 flex items-center justify-between gap-4"><h2 id="history-reference-title" className="font-medium">{'memory_id' in reference ? 'Saved memory' : history?.title ?? 'Past conversation'}</h2><Button variant="ghost" size="sm" onClick={onClose}>Close reference</Button></div>
    {error ? <p role="alert">This reference is unavailable. It may have been deleted. {error}</p> : !memory && !history ? <div role="status"><Spinner />Loading reference…</div> : null}
    {memory && <><p className="mb-4 whitespace-pre-wrap text-body">{memory.content}</p>{'revision' in reference && reference.revision !== memory.revision && <p className="mb-4 text-sm text-muted">This memory has changed since the answer. Showing the current version.</p>}<MemoryDetails memory={memory} /><Link className="mt-5 inline-block text-accent underline" to={`/settings?tab=memories&memory=${memory.id}`} onClick={onClose}>Manage this memory</Link></>}
    {history && <><div className="space-y-5">{history.messages.map(message => <section key={message.id} className="rounded-xl border border-border p-4"><p className="mb-2 text-xs text-muted">{message.role === 'user' ? 'You' : 'Mentra'} · {new Date(message.created_at).toLocaleString()}{message.exchange_status === 'FAILED' ? ' ? Response failed' : message.exchange_status === 'RUNNING' ? ' ? Response in progress' : ''}</p><MarkdownContent content={message.content} /></section>)}</div><Link className="mt-5 inline-block text-accent underline" to={`/chat/${history.conversation_id}`} onClick={onClose}>Open conversation</Link></>}
  </dialog>;
}
