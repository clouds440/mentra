import { useState } from 'react';
import { Button } from '../ui/Button';
import { Textarea } from '../ui/Textarea';
import { Select } from '../ui/Select';
import type { UserMemory } from '../../types/memories';

export function MemoryEditor({ memory, busy, onSave, onCancel }: {
  memory?: UserMemory; busy: boolean;
  onSave: (content: string, category: string) => Promise<void>; onCancel: () => void;
}) {
  const [content, setContent] = useState(memory?.content ?? '');
  const [category, setCategory] = useState(memory?.category ?? 'fact');
  return <form className="space-y-4 rounded-xl border border-border bg-surface p-4" onSubmit={event => { event.preventDefault(); void onSave(content.trim(), category); }}>
    <label className="block text-sm font-medium text-heading">Memory
      <Textarea autoFocus className="mt-2" disabled={busy} value={content} onChange={event => setContent(event.target.value)} maxLength={500} required rows={4} aria-describedby="memory-editor-help" />
    </label>
    <p id="memory-editor-help" className="text-xs text-muted">Keep one clear fact, preference or goal. {content.length}/500 characters. Manual entries are your own assertions.</p>
    {!memory && <label className="block text-sm text-heading">Category<Select className="mt-2" disabled={busy} value={category} onChange={event => setCategory(event.target.value as UserMemory['category'])}><option value="fact">Fact</option><option value="preference">Preference</option><option value="goal">Goal</option></Select></label>}
    <div className="flex gap-2"><Button type="submit" disabled={busy || !content.trim()}>{busy ? 'Saving…' : 'Save memory'}</Button><Button variant="ghost" disabled={busy} onClick={onCancel}>Cancel</Button></div>
  </form>;
}
