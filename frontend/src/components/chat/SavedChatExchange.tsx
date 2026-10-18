import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MessageSquare, ArrowUpRight } from 'lucide-react';
import { savedExchange } from '../../services/conversations';
import { ApiError } from '../../services/api';
import type { SavedExchange } from '../../types/conversations';
import { Dialog } from '../ui/Dialog';
import { Button, buttonStyles } from '../ui/Button';
import { Skeleton } from '../ui/Skeleton';
import { MarkdownContent } from '../content/MarkdownContent';
import { CopyResponse } from './CopyResponse';

export function SavedChatExchange({ conversation, message, onClose }: { conversation: string; message: string; onClose: () => void }) {
  const [data, setData] = useState<SavedExchange>(), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  const match = useRef<HTMLElement>(null), reader = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const controller = new AbortController(); setData(undefined); setError('');
    void savedExchange(conversation, message, controller.signal).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to open this exchange. Try again.'); });
    return () => controller.abort();
  }, [conversation, message, retry]);
  useEffect(() => {
    if (!data) return;
    const frame = requestAnimationFrame(() => { if (match.current && reader.current) {
      reader.current.scrollTop += match.current.getBoundingClientRect().top - reader.current.getBoundingClientRect().top - 16;
      match.current.focus({preventScroll:true});
    } });
    return () => cancelAnimationFrame(frame);
  }, [data]);
  return <Dialog open onDismiss={onClose} aria-labelledby="saved-exchange-title" className="m-auto flex max-h-[88dvh] w-[calc(100%-1.5rem)] max-w-3xl flex-col overflow-hidden rounded-panel border border-border bg-popover p-0 text-foreground shadow-overlay">
    <header className="shrink-0 border-b border-border p-4 sm:p-5"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="mb-1 flex items-center gap-1.5 text-xs text-accent"><MessageSquare size={14} aria-hidden="true" />Saved exchange</p><h2 id="saved-exchange-title" className="break-words font-semibold text-heading">{data?.title ?? 'Opening your chat…'}</h2></div><Button size="sm" variant="ghost" onClick={onClose}>Close</Button></div></header>
    <div ref={reader} className="min-h-0 space-y-4 overflow-y-auto overscroll-contain p-4 sm:p-5">
      {error ? <p role="alert" className="text-sm text-danger">{error} <Button size="sm" variant="ghost" onClick={() => setRetry(value => value+1)}>Retry exchange</Button></p> : !data ? <Skeleton variant="text" rows={8} /> : data.messages.map(item => <section key={item.id} ref={item.id===message ? match : undefined} tabIndex={item.id===message ? -1 : undefined} aria-label={item.id===message ? 'Matching message' : 'Neighboring message'} className={`min-w-0 space-y-3 rounded-panel border p-3 sm:p-4 ${item.id===message ? 'border-accent/50 bg-active focus:outline-none focus:ring-2 focus:ring-accent' : 'border-border bg-surface'}`}>
        <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-medium text-muted">{item.role==='user' ? 'You' : 'Mentra'} · {new Date(item.created_at).toLocaleString()}</p><CopyResponse content={item.content} subject={item.role==='user' ? 'message' : 'response'} /></div><MarkdownContent content={item.content} />
      </section>)}
    </div>
    <footer className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border p-4"><p className="text-xs text-muted">Original messages from this part of your chat.</p><Link className={buttonStyles({variant:'secondary',size:'sm'})} to={`/chat/${encodeURIComponent(conversation)}`} onClick={onClose}>Continue chat<ArrowUpRight size={14} aria-hidden="true" /></Link></footer>
  </Dialog>;
}
