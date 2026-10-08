import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, Input, Select } from '../ui';
import { createContext, uploadMaterial, materialError } from '../../services/rag';
import type { LearningContext, MaterialDocument, RAGCapabilities } from '../../types/rag';

export function MaterialUpload({ contexts, capabilities, replacement, onAccepted, onContextCreated }: { contexts: LearningContext[]; capabilities: RAGCapabilities; replacement?: MaterialDocument; onAccepted: (id: string, duplicate: boolean) => void; onContextCreated: () => void }) {
  const [file, setFile] = useState<File | null>(null); const [title, setTitle] = useState(''); const [contextId, setContextId] = useState('');
  const [newName, setNewName] = useState(''); const [activate, setActivate] = useState(true);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const controller = useRef<AbortController>(); const key = useRef(crypto.randomUUID()); const input = useRef<HTMLInputElement>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!file || busy) return;
    if (file.size > capabilities.max_upload_bytes) { setError('This file exceeds the upload size limit.'); return; }
    if (!replacement && !contextId && !newName.trim()) { setError('Choose or create a learning context.'); return; }
    setBusy(true); setError(''); const abort = new AbortController(); controller.current = abort;
    try {
      let selected = contextId;
      if (!replacement && !selected) { const context = await createContext(newName.trim(), activate); selected = context.context_id; setContextId(selected); onContextCreated(); }
      if (abort.signal.aborted) return;
      const result = await uploadMaterial(file, title, replacement?.context_ids ?? [selected], key.current, abort.signal, replacement);
      if (abort.signal.aborted) return;
      setFile(null); setTitle(''); if (input.current) input.current.value = ''; key.current = crypto.randomUUID(); onAccepted(result.document_id, result.duplicate);
    } catch (e) { if (!abort.signal.aborted) setError(materialError(e)); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }
  return <form aria-label={replacement ? 'Replace material' : 'Add material'} onSubmit={e => void submit(e)} className="space-y-4 rounded-2xl border border-border bg-surface p-5">
    <h2 className="font-medium">{replacement ? 'Upload a revised version' : 'Add study material'}</h2>
    <p className="text-sm text-muted">{capabilities.formats.map(f => f.toUpperCase()).join(', ')} · Up to {Math.floor(capabilities.max_upload_bytes / 1024 / 1024)} MiB. Processing continues after upload.</p>
    <label className="block text-sm">File<Input ref={input} type="file" className="mt-2" required disabled={busy} accept={capabilities.formats.map(f => `.${f}`).join(',')} onChange={e => { setFile(e.target.files?.[0] ?? null); key.current = crypto.randomUUID(); }} /></label>
    {!replacement && <><label className="block text-sm">Material title<Input className="mt-2" value={title} maxLength={200} disabled={busy} placeholder="Use the filename if left blank" onChange={e => { setTitle(e.target.value); key.current = crypto.randomUUID(); }} /></label>
    <label className="block text-sm">Learning context<Select className="mt-2" value={contextId} disabled={busy} onChange={e => { setContextId(e.target.value); key.current = crypto.randomUUID(); }}><option value="">Create a context</option>{contexts.filter(c => c.status !== 'ARCHIVED').map(c => <option key={c.context_id} value={c.context_id}>{c.name} ({c.status.toLowerCase()})</option>)}</Select></label>
    {!contextId && <><label className="block text-sm">New context name<Input className="mt-2" value={newName} maxLength={200} disabled={busy} onChange={e => setNewName(e.target.value)} /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={activate} disabled={busy} onChange={e => setActivate(e.target.checked)} />Make this my current learning context</label></>}</>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <Button type="submit" disabled={!file || busy}>{busy ? 'Uploading…' : replacement ? 'Submit replacement' : 'Upload material'}</Button>
  </form>;
}
