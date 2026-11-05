import { buttonStyles } from '../ui/Button';
import { SourceMarkdownLink } from '../webSearch/SourceLink';
import { ApiError } from '../../services/api';
import { Skeleton } from '../ui/Skeleton';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { memoryApi } from '../../services/memories';
import type { HistoryReference, MemoryReference, HistoryWindow, UserMemory } from '../../types/memories';

import { MemoryDetails } from '../memories/MemoryDetails';
import { MarkdownContent } from '../content/MarkdownContent';

export function HistoryReferenceContent({ reference, onClose }: { reference: HistoryReference | MemoryReference; onClose: () => void }) {
  const [history, setHistory] = useState<HistoryWindow>();
  const [memory, setMemory] = useState<UserMemory>();
  const [error, setError] = useState('');
  useEffect(() => {

    const controller = new AbortController();
    if ('memory_id' in reference) {
      memoryApi.detail(reference.memory_id, controller.signal).then(value => { if (!controller.signal.aborted) setMemory(value); }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof ApiError ? cause.message : 'This reference could not be loaded.'); });
    } else {
      memoryApi.history(reference.conversation_id, reference.sequence, controller.signal).then(value => { if (!controller.signal.aborted) setHistory(value); }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof ApiError ? cause.message : 'This reference could not be loaded.'); });
    }
    return () => controller.abort();
  }, [reference]);
  return <div className="space-y-4 p-4">
    <div className="mb-5 flex items-center justify-between gap-4"><h2 className="font-medium">{'memory_id' in reference ? 'Saved memory' : history?.title ?? 'Past conversation'}</h2></div>
    {error ? <p role="alert">{error}</p> : !memory && !history ? <Skeleton variant="text" /> : null}
    {memory && <><p className="mb-4 whitespace-pre-wrap text-body">{memory.content}</p>{'revision' in reference && reference.revision !== memory.revision && <p className="mb-4 text-sm text-muted">This memory has changed since the answer. Showing the current version.</p>}<MemoryDetails memory={memory} /><Link className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'mt-5' })} to={`/settings?tab=memories&memory=${memory.id}`} onClick={onClose}>Manage this memory</Link></>}
    {history && <><div className="space-y-5">{history.messages.map(message => <section key={message.id} className="rounded-xl border border-border p-4"><p className="mb-2 text-xs text-muted">{message.role === 'user' ? 'You' : 'Mentra'} · {new Date(message.created_at).toLocaleString()}{message.exchange_status === 'FAILED' ? ' ? Response failed' : message.exchange_status === 'RUNNING' ? ' ? Response in progress' : ''}</p><MarkdownContent content={message.content} linkComponent={SourceMarkdownLink} /></section>)}</div><Link className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'mt-5' })} to={`/chat/${history.conversation_id}`} onClick={onClose}>Open conversation</Link></>}
  </div>;
}
