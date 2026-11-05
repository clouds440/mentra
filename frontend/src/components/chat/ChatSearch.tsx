import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { Search, MessageSquare, ArrowUpRight, X } from 'lucide-react';
import { Button, IconButton, Input } from '../ui';
import { Dialog } from '../ui/Dialog';
import { Skeleton } from '../ui/Skeleton';
import { useAuth } from '../auth/AuthProvider';
import { searchChats } from '../../services/conversations';
import { ApiError } from '../../services/api';
import type { ChatSearchPage } from '../../types/conversations';

export function ChatSearch({ onOpen }: { onOpen: () => void }) {
  const { identity } = useAuth();
  const [params, setParams] = useSearchParams();
  const open = params.get('search_open') === '1';
  const text = params.get('chat_search') ?? '';
  const offset = Math.min(180, Math.max(0, Number(params.get('chat_search_offset')) || 0));
  const results = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState(text.trim()), [data, setData] = useState<ChatSearchPage>();
  const [loaded, setLoaded] = useState(''), [loading, setLoading] = useState(false), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const key = JSON.stringify([identity?.learner_id, query, offset]);
  const visible = loaded === key && query === text.trim() ? data : undefined;
  useEffect(() => { if (!open) return; const frame = requestAnimationFrame(() => input.current?.focus()); return () => cancelAnimationFrame(frame); }, [open]);
  useEffect(() => { const timer = setTimeout(() => setQuery(text.trim()), 300); return () => clearTimeout(timer); }, [text]);
  useEffect(() => {
    if (!open || !query || query !== text.trim()) return;
    const controller = new AbortController(); setLoading(true); setError('');
    void searchChats(query, offset, controller.signal).then(value => {
      if (!controller.signal.aborted) { setData(value); setLoaded(key); }
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Unable to search your chats. Try again.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, key, text, retry]);
  useEffect(() => { if (results.current) results.current.scrollTop = 0; }, [query, offset]);
  function close() { const next = new URLSearchParams(params); next.delete('search_open'); setParams(next, {replace:true}); }
  function page(value: number) { const next = new URLSearchParams(params); next.set('chat_search_offset', String(value)); setParams(next, {replace:true}); }
  function changeSearch(value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set('chat_search', value);
    else next.delete('chat_search');
    next.delete('chat_search_offset');
    setError('');
    setParams(next, { replace: true });
  }
  return <>
    <IconButton size="sm" aria-label="Search saved chats" title="Search saved chats" className="mr-1 text-inherit" onClick={() => { const next = new URLSearchParams(params); next.set('search_open','1'); next.delete('message'); setParams(next); }}><Search size={15} aria-hidden="true" /></IconButton>
    {open && <Dialog open onDismiss={close} aria-labelledby="chat-search-title" aria-describedby="chat-search-description" layout="viewer" className="chat-search-dialog max-w-2xl" heading={<h2 id="chat-search-title" className="flex items-center gap-2"><Search size={17} aria-hidden="true" />Search your chats</h2>}>
      <div className="chat-search-fields">
        <p id="chat-search-description" className="text-xs text-muted">Find a phrase in your saved messages or chat titles.</p>
        <div className="chat-search-input">
          {text && <IconButton size="sm" aria-label="Clear chat search" onClick={() => { changeSearch(''); input.current?.focus(); }}><X size={15} aria-hidden="true" /></IconButton>}
          <Input ref={input} autoFocus type="search" aria-label="Search chat titles and messages" placeholder="A topic, phrase or question…" maxLength={200} value={text} onChange={event => changeSearch(event.target.value)} />
        </div>
      </div>
      <div ref={results} className="chat-search-results" aria-live="polite" aria-busy={!!text.trim() && (!visible && !error || loading)}>
        {!text.trim() ? <div className="px-4 py-10 text-center"><MessageSquare size={28} className="mx-auto mb-3 text-subtle" aria-hidden="true" /><p className="text-sm text-heading">Find your way back to an idea</p><p className="mt-1 text-xs text-muted">Search across all your saved chats, including older conversations.</p></div> : error ? <p role="alert" className="p-3 text-sm text-danger">{error} <Button size="sm" variant="ghost" onClick={() => setRetry(value => value+1)}>Retry search</Button></p> : !visible ? <Skeleton variant="list" rows={4} /> : <>
          {!visible.items.length && <div className="px-4 py-8 text-center"><p className="text-sm font-medium text-heading">No matching chats</p><p className="mt-1 text-xs text-muted">Try a shorter phrase or a different word.</p></div>}
          <ul className="divide-y divide-border" aria-label="Chat search results">{visible.items.map(hit => <li key={hit.matched_message_id}><Link onClick={onOpen} to={`/chat/${encodeURIComponent(hit.conversation_id)}?${new URLSearchParams({message:hit.matched_message_id,chat_search:text})}`} className="block rounded-control px-3 py-3.5 hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent">
            <div className="flex items-start gap-2"><span className="min-w-0 flex-1 break-words text-sm font-medium text-heading">{hit.title}</span><ArrowUpRight size={15} className="shrink-0 text-subtle" aria-hidden="true" /></div>
            <p className="mt-1.5 line-clamp-3 whitespace-pre-wrap break-words text-xs leading-5 text-muted">{hit.snippet}</p><p className="mt-2 text-[10px] text-subtle">{hit.role==='user' ? 'You' : 'Mentra'} · {new Date(hit.created_at).toLocaleDateString()}{hit.matched_in==='title' ? ' · Title match' : ''}</p>
          </Link></li>)}</ul>
          {(offset>0 || visible.next_offset!==null) && <nav aria-label="Chat search pages" className="mt-4 flex justify-between gap-3"><Button size="sm" variant="secondary" disabled={loading || offset===0} onClick={() => page(offset-20)}>Previous results</Button><Button size="sm" variant="secondary" disabled={loading || visible.next_offset===null} onClick={() => page(visible.next_offset!)}>Next results</Button></nav>}
          {visible.truncated && <p className="mt-3 text-xs text-muted">Showing the first 200 matches. Use a more specific phrase to narrow your results.</p>}
        </>}
      </div>
    </Dialog>}
  </>;
}
