import { Link } from 'react-router-dom';
import type { UserMemory } from '../../types/memories';

export function MemoryDetails({ memory }: { memory: UserMemory }) {
  return <div className="space-y-3 text-sm text-muted">
    <p>Saved {new Date(memory.created_at).toLocaleDateString()} · {memory.origin === 'manual' ? 'Added or edited by you' : 'Proposed by Mentra'}</p>
    {memory.confirmed_at && <p>Confirmed {new Date(memory.confirmed_at).toLocaleDateString()}</p>}
    {memory.expires_at && <p>{memory.stale ? 'Needs review since' : 'Review after'} {new Date(memory.expires_at).toLocaleDateString()}. Pinning does not make an old fact current.</p>}
    {memory.conflicts.length > 0 && <div><p className="font-medium text-heading">Conflicting saved statements</p><ul className="mt-2 space-y-2">{memory.conflicts.map(item => <li key={item.memory_id} className="rounded-lg border border-border p-3">{item.content}</li>)}</ul></div>}
    {memory.evidence?.map(item => <div className="rounded-lg border border-border p-3" key={item.id}>
      <p className="whitespace-pre-wrap break-words text-body">“{item.quote}”</p>
      <p className="mt-2 text-xs">{new Date(item.source_date).toLocaleDateString()} · {item.source_deleted ? 'Source chat deleted; saved evidence retained' : item.conversation_id ? 'User statement' : 'Manual entry'}</p>
      {!item.source_deleted && item.conversation_id && <Link className="mt-2 inline-block text-accent hover:underline" to={`/chat/${item.conversation_id}`}>Open source conversation</Link>}
    </div>)}
  </div>;
}
