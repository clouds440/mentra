import { Toggle } from '../ui/Toggle';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, FileInput, Input, Select, FormField, IconButton, Skeleton } from '../ui';
import { FileText, X, Upload, ArrowRight, Check } from 'lucide-react';
import { createContext, uploadMaterial, materialError } from '../../services/rag';
import type { LearningContext, MaterialDocument, RAGCapabilities } from '../../types/rag';

const fileSize = (bytes: number) => bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KiB` : `${(bytes / 1024 / 1024).toFixed(1)} MiB`;

export function MaterialUploadSkeleton() {
  return <div className="material-upload" role="status" aria-label="Loading upload form"><div className="material-upload-body"><div className="material-upload-file"><Skeleton rows={2} /><div className="file-dropzone mt-6"><Skeleton className="max-w-48" rows={3} /></div><div className="upload-file-summary"><Skeleton rows={1} /></div></div><div className="material-upload-details"><Skeleton rows={2} /><Skeleton variant="form" rows={3} /></div></div><div className="material-upload-footer"><Skeleton variant="button" /></div></div>;
}

export function MaterialUpload({ contexts, capabilities, replacement, onAccepted, onContextCreated }: { contexts: LearningContext[]; capabilities: RAGCapabilities; replacement?: MaterialDocument; onAccepted: (id: string, duplicate: boolean) => void; onContextCreated: () => void }) {
  const [file, setFile] = useState<File | null>(null); const [title, setTitle] = useState(''); const [contextId, setContextId] = useState('');
  const [newName, setNewName] = useState(''); const [activate, setActivate] = useState(true);
  const [contextMode, setContextMode] = useState<'existing' | 'new'>(() => contexts.some(context => context.status !== 'ARCHIVED') ? 'existing' : 'new');
  const [createdContext, setCreatedContext] = useState<LearningContext>();
  const availableContexts = createdContext && !contexts.some(context => context.context_id === createdContext.context_id) ? [...contexts, createdContext] : contexts;
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const controller = useRef<AbortController>(); const key = useRef(crypto.randomUUID()); const input = useRef<HTMLInputElement>(null);
  useEffect(() => () => controller.current?.abort(), []);
  function chooseFiles(files: File[]) {
    if (!files.length) { setFile(null); setError(''); return; }
    if (files.length !== 1 || files[0].size > capabilities.max_upload_bytes || files[0].size === 0) {
      setError(files.length !== 1 ? 'Choose one file at a time.' : files[0].size === 0 ? 'This file is empty. Choose a file with content.' : 'This file exceeds the upload size limit.');
      setFile(null); if (input.current) input.current.value = ''; return;
    }
    setFile(files[0]); setError(''); key.current = crypto.randomUUID();
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!file || busy) return;
    if (file.size > capabilities.max_upload_bytes) { setError('This file exceeds the upload size limit.'); return; }
    if (!replacement && (contextMode === 'existing' ? !contextId : !newName.trim())) { setError('Choose or create a learning context.'); return; }
    setBusy(true); setError(''); const abort = new AbortController(); controller.current = abort;
    try {
      let selected = contextMode === 'existing' ? contextId : '';
      if (!replacement && !selected) { const context = await createContext(newName.trim(), activate, abort.signal); selected = context.context_id; setCreatedContext(context); setContextId(selected); setContextMode('existing'); onContextCreated(); }
      if (abort.signal.aborted) return;
      const result = await uploadMaterial(file, title, replacement?.context_ids ?? [selected], key.current, abort.signal, replacement);
      if (abort.signal.aborted) return;
      setFile(null); setTitle(''); if (input.current) input.current.value = ''; key.current = crypto.randomUUID(); onAccepted(result.document_id, result.duplicate);
    } catch (e) { if (!abort.signal.aborted) setError(materialError(e)); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }
  return <form aria-label={replacement ? 'Replace material' : 'Add material'} onSubmit={e => void submit(e)} className="material-upload" aria-busy={busy}>
    <div className="material-upload-body">
      <section className="material-upload-file" aria-label="Choose your file">
        <div className="library-section-heading"><span className="library-step">01</span><div><h2>{replacement ? 'Upload a revised version' : 'Choose your source'}</h2><p>Bring the material you want to learn from.</p></div></div>
        <FileInput ref={input} label="File" variant="dropzone" filename={file?.name ?? ''} required disabled={busy} hint={`One file · up to ${fileSize(capabilities.max_upload_bytes)}`} onFiles={chooseFiles} />
        <div className="upload-file-summary" aria-live="polite">{file ? <><FileText size={21} className="shrink-0 text-accent" aria-hidden="true" /><div className="min-w-0 flex-1"><p className="break-all text-sm font-medium text-heading">{file.name}</p><p className="mt-1 text-xs text-muted">{file.size < 1024 * 1024 ? `${Math.ceil(file.size / 1024)} KiB` : `${(file.size / 1024 / 1024).toFixed(1)} MiB`} · Ready to upload</p></div><IconButton aria-label="Remove selected file" disabled={busy} onClick={() => { setFile(null); setError(''); if (input.current) input.current.value = ''; }}><X size={16} /></IconButton></> : <p className="text-sm text-muted">Your selected file will appear here.</p>}</div>
        <details className="upload-formats"><summary>Supported file types</summary><p>{capabilities.formats.map(format => format.toUpperCase()).join(' · ')}</p></details>
      </section>
      <section className="material-upload-details" aria-label="Material details">
        <div className="library-section-heading"><span className="library-step">02</span><div><h2>{replacement ? 'Keep your source up to date' : 'Make it easy to find'}</h2><p>{replacement ? 'A new version, in the same place.' : 'Give it a name and a learning context.'}</p></div></div>
        {replacement ? <div className="space-y-4 text-sm leading-6 text-muted"><p className="font-medium text-heading break-words">{replacement.title}</p><p>The revised file joins this material’s version history. Earlier source versions remain available.</p><p>Mentra prepares the new version after upload. The current source stays available while it processes.</p></div> : <>
          <FormField label="Material title" hint="Optional. Leave blank to use the filename.">{field => <Input {...field} value={title} maxLength={200} disabled={busy} placeholder={file?.name || 'e.g. Biology revision notes'} onChange={event => { setTitle(event.target.value); key.current = crypto.randomUUID(); }} />}</FormField>
          <fieldset className="min-w-0 space-y-3" disabled={busy}><legend className="mb-2 text-sm font-medium text-heading">Learning context</legend><div className="upload-context-options">{(['existing', 'new'] as const).map(mode => <label key={mode}><input type="radio" name="context-mode" value={mode} checked={contextMode === mode} onChange={() => { setContextMode(mode); key.current = crypto.randomUUID(); }} /><span>{mode === 'existing' ? 'Use existing' : 'Create new'}</span></label>)}</div>
            <div className="upload-context-fields">{contextMode === 'existing' ? <FormField label="Choose a learning context" hint="Group related sources so they’re easier to study together.">{field => <Select {...field} value={contextId} required onChange={event => { setContextId(event.target.value); key.current = crypto.randomUUID(); }}><option value="">Select a context…</option>{availableContexts.filter(context => context.status !== 'ARCHIVED').map(context => <option key={context.context_id} value={context.context_id}>{context.name}</option>)}</Select>}</FormField> : <div className="space-y-4"><FormField label="New context name">{field => <Input {...field} value={newName} required maxLength={200} placeholder="e.g. Biology or English practice" onChange={event => setNewName(event.target.value)} />}</FormField><Toggle label="Make this my current learning context" checked={activate} onChange={event => setActivate(event.target.checked)} /></div>}</div>
          </fieldset>
        </>}
        <div className="upload-next"><Check size={16} aria-hidden="true" /><p>Once ready, study this source in chat or build a practice assessment from it.</p></div>
      </section>
    </div>
    <footer className="material-upload-footer"><div className="min-w-0"><p className="text-sm font-medium text-heading">{busy ? 'Uploading your source…' : 'Ready when you are'}</p><p className="mt-1 text-xs text-muted">Processing continues after upload. You can leave this page once it’s accepted.</p>{file && (/\.(pdf|png|jpe?g)$/i.test(file.name) || file.type === 'application/pdf' || file.type.startsWith('image/')) && <p role="status" aria-label="OCR upload notice" className="mt-2 text-xs text-muted">{capabilities.image_ocr === false ? 'Image-based text cannot be read on this server. Your original can be stored, but scanned content will not be searchable.' : 'Scanned pages and images use OCR. Some text may be missed or misread. Check important content against the original.'}</p>}{error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}</div><Button type="submit" disabled={!file || busy} loading={busy}><Upload size={16} aria-hidden="true" />{replacement ? 'Submit replacement' : 'Upload material'}<ArrowRight size={15} aria-hidden="true" /></Button></footer>
  </form>;
}
