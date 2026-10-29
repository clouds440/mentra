import { buttonStyles } from '../ui/Button';
import { Button } from '../ui/Button';
import { useEffect, useRef, useState } from 'react';
import { memoryApi } from '../../services/memories';
import { Link } from 'react-router-dom';
import type { MemoryRevision, UserMemory } from '../../types/memories';

export function MemoryDetails({ memory, busy = false, onRestore }: { memory: UserMemory; busy?: boolean; onRestore?: (revision: number) => void }) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<MemoryRevision[]>([]);
  const [before, setBefore] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    request.current?.abort();
    setOpen(false); setHistory([]); setBefore(null); setError(''); setLoading(false);
    return () => request.current?.abort();
  }, [memory.id, memory.revision]);
  async function load(cursor?: number) {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError(''); setOpen(true);
    try {
      const page = await memoryApi.revisions(memory.id, cursor, controller.signal);
      if (!controller.signal.aborted) { setHistory(previous => cursor ? [...previous, ...page.items] : page.items); setBefore(page.next_before); }
    } catch {
      if (!controller.signal.aborted) setError('Memory history could not be loaded. Please try again.');
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }
  return <div className="space-y-3 text-sm text-muted">
    <p>Saved {new Date(memory.created_at).toLocaleDateString()} · {memory.origin === 'manual' ? 'Added or edited by you' : 'Proposed by Mentra'}</p>
    {memory.confirmed_at && <p>Confirmed {new Date(memory.confirmed_at).toLocaleDateString()}</p>}
    {memory.expires_at && <p>{memory.stale ? 'Needs review since' : 'Review after'} {new Date(memory.expires_at).toLocaleDateString()}. Pinning does not make an old fact current.</p>}
    {memory.conflicts.length > 0 && <div><p className="font-medium text-heading">Conflicting saved statements</p><ul className="mt-2 space-y-2">{memory.conflicts.map(item => <li key={item.memory_id} className="rounded-lg border border-border p-3">{item.content}</li>)}</ul></div>}
    {memory.evidence?.map(item => <div className="rounded-lg border border-border p-3" key={item.id}>
      <p className="whitespace-pre-wrap break-words text-body">“{item.quote}”</p>
      <p className="mt-2 text-xs">{new Date(item.source_date).toLocaleDateString()} · {item.source_deleted ? 'Source chat deleted; saved evidence retained' : item.conversation_id ? 'User statement' : 'Manual entry'}</p>
      {!item.source_deleted && item.conversation_id && <Link className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'mt-2' })} to={`/chat/${item.conversation_id}`}>Open source conversation</Link>}
    </div>)}
    <Button variant="secondary" size="sm" disabled={loading} onClick={() => open ? setOpen(false) : void load()}> {open ? 'Hide history' : 'View history'}</Button>
    {open && <div aria-label="Memory revision history" className="space-y-3">
      <p>Restoring earlier wording saves a new version. Your history stays available.</p>
      {history.map(item => <div key={item.revision} className="rounded-lg border border-border p-3">
        <p className="text-xs">Version {item.revision} · {new Date(item.created_at).toLocaleString()} · {item.actor === 'ai' ? 'Mentra' : 'You'}</p>
        <p className="mt-2 whitespace-pre-wrap break-words text-body">{item.snapshot?.content ?? 'Content was not recorded for this older version.'}</p>
        {item.evidence.map(evidence => <blockquote key={evidence.id} className="mt-2 border-l-2 border-border pl-3 text-xs">“{evidence.quote}”</blockquote>)}
        {onRestore && item.snapshot && item.revision !== memory.revision && memory.status !== 'conflict' && <Button variant="secondary" size="sm" className="mt-2" disabled={busy} onClick={() => onRestore(item.revision)}>Restore this version</Button>}
      </div>)}
      {loading && <p role="status">Loading history…</p>}
      {error && <p role="alert">{error}</p>}
      {error && <Button variant="secondary" size="sm" disabled={loading} onClick={() => void load(history.length ? before ?? undefined : undefined)}>Retry history</Button>}
      {before && !error && <Button variant="secondary" size="sm" disabled={loading} onClick={() => void load(before)}>Older versions</Button>}
    </div>}
  </div>;
}
