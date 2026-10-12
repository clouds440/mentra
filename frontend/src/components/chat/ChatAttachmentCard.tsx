import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Image as ImageIcon, LibraryBig } from 'lucide-react';
import { getChatAttachment, getChatAttachmentSource, saveChatAttachment } from '../../services/chatAttachments';
import type { AttachmentDetail, ChatAttachment } from '../../services/chatAttachments';
import { createContext, listContexts } from '../../services/rag';
import type { LearningContext } from '../../types/rag';
import { Button, Input, Select } from '../ui';
import { ChatAttachmentPreview, type AttachmentOriginal } from './ChatAttachmentPreview';
import { fileLanguage } from '../../lib/codeLanguages';

export function ChatAttachmentCard({ file, conversationId }: { file: ChatAttachment; conversationId: string }) {
  const [loadingContexts, setLoadingContexts] = useState(false);
  const [detail, setDetail] = useState<AttachmentDetail>();
  const [choosing, setChoosing] = useState(false), [busy, setBusy] = useState(false);
  const [contexts, setContexts] = useState<LearningContext[]>([]), [context, setContext] = useState('');
  const [error, setError] = useState<string>();
  const [newContext, setNewContext] = useState('');
  const [original, setOriginal] = useState<AttachmentOriginal>();
  const [opened, setOpened] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const card = useRef<HTMLDivElement>(null);
  const source = useRef<{controller: AbortController; pending?: Promise<AttachmentOriginal>; original?: AttachmentOriginal}>({controller:new AbortController()});
  const isImage = /\.(png|jpe?g|gif|webp)$/i.test(file.filename);
  const format = /\.([a-z0-9]{1,8})$/i.exec(file.filename)?.[1].toUpperCase() || 'FILE';
  useEffect(() => {
    const current = {controller:new AbortController()} as typeof source.current;
    source.current = current; setOriginal(undefined); setImageFailed(false);
    return () => { current.controller.abort(); if (current.original) URL.revokeObjectURL(current.original.url); };
  }, [file.id, conversationId]);
  const loadOriginal = useCallback(async () => {
    const current = source.current;
    if (current.original) return current.original;
    if (current.pending) return current.pending;
    const pending = getChatAttachmentSource(file.id, conversationId, current.controller.signal).then(async blob => {
      const image = ['image/png','image/jpeg','image/gif','image/webp'].includes(blob.type);
      const textual = !image && blob.type !== 'application/pdf' && !blob.type.includes('officedocument') && (!!fileLanguage(file.filename) || blob.type.startsWith('text/') || ['application/json','application/xml','application/yaml'].includes(blob.type));
      const limit = 256 * 1024;
      const text = textual ? new TextDecoder().decode(await blob.slice(0, limit).arrayBuffer(), {stream:blob.size > limit}) : undefined;
      if (current.controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const value = {blob, url:URL.createObjectURL(blob), image, text, truncated:textual && blob.size > limit};
      current.original = value; setOriginal(value); return value;
    });
    current.pending = pending;
    try { return await pending; } finally { if (current.pending === pending) current.pending = undefined; }
  }, [file.id, conversationId, file.filename]);
  useEffect(() => {
    if (!isImage || !card.current) return;
    let active = true, retries = 0, timer: ReturnType<typeof setTimeout>;
    async function preview() {
      try { await loadOriginal(); }
      catch { if (active && retries++ < 3) timer = setTimeout(() => void preview(), 1000 * retries); }
    }
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect(); void preview();
    }, {rootMargin:'100px'});
    observer.observe(card.current);
    return () => { active=false; observer.disconnect(); clearTimeout(timer); };
  }, [isImage, loadOriginal]);
  const action = useRef<AbortController | null>(null);
  useEffect(() => () => action.current?.abort(), [file.id, conversationId]);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>, retries = 0;
    setDetail(undefined);
    async function refresh() {
      try {
        const value = await getChatAttachment(file.id, conversationId, controller.signal);
        if (controller.signal.aborted) return;
        setDetail(value);
        if (!value.ready && !value.error && retries++ < 80) timer = setTimeout(() => void refresh(), 2000);
      } catch (e) {
        if (!controller.signal.aborted) {
          // Background metadata can race chat publication or reconnect. Keep
          // retries quiet; report errors only for explicit user actions.
          if (retries++ < 4) timer = setTimeout(() => void refresh(), 2000);
        }
      }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [file.id, conversationId]);
  async function choose() {
    action.current?.abort(); const controller = new AbortController(); action.current = controller;
    setChoosing(true); setLoadingContexts(true); setError(undefined);
    try { const result = await listContexts(controller.signal); if (!controller.signal.aborted) setContexts(result.filter(item => item.status !== 'ARCHIVED')); }
    catch (e) { if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Could not load learning contexts.'); }
    finally { if (!controller.signal.aborted) setLoadingContexts(false); }
  }
  async function save() {
    action.current?.abort(); const controller = new AbortController(); action.current = controller;
    setBusy(true); setError(undefined);
    try {
      const result = await saveChatAttachment(file.id, conversationId, [context], controller.signal);
      if (!controller.signal.aborted) { setDetail(value => value && ({ ...value, library_result: result })); setChoosing(false); }
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Could not save this file.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function addContext() {
    action.current?.abort(); const controller = new AbortController(); action.current = controller;
    setBusy(true); setError(undefined);
    try {
      const result = await createContext(newContext.trim(), true, controller.signal);
      if (!controller.signal.aborted) { setContexts(previous => [...previous, result]); setContext(result.context_id); setNewContext(''); }
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Could not create learning context.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <div ref={card} className={`flex max-w-full flex-col items-end gap-1 text-sm ${choosing ? 'w-72' : 'w-fit'}`} aria-label={`Attachment ${file.filename}`}>
    <button type="button" aria-label={`Open ${file.filename}`} className="block max-w-full overflow-hidden rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background" onClick={() => setOpened(true)}>
      {original?.image && !imageFailed ? <img src={original.url} alt={file.filename} className="block h-auto max-h-72 w-auto max-w-[min(20rem,100%)]" onError={() => setImageFailed(true)} /> : <span className="flex h-32 w-48 max-w-full flex-col items-center justify-center gap-2 rounded-xl border border-border bg-surface text-muted">{isImage ? <ImageIcon size={28} aria-hidden="true" /> : <FileText size={28} aria-hidden="true" />}<span className="text-xs font-medium">{isImage ? 'Image' : format+' document'}</span></span>}
    </button>
    <div className="flex w-full justify-end">
      {detail?.library_result ? <Link className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-border-strong bg-hover px-2.5 text-xs font-medium text-foreground hover:bg-active focus-visible:ring-2 focus-visible:ring-accent" to={`/library/${detail.library_result.document_id}`}><LibraryBig size={13} aria-hidden="true" />View in Library</Link>
        : <Button className="min-h-8 !px-2.5 text-xs" size="sm" variant="secondary" disabled={!detail?.ready || busy} onClick={() => void choose()}><LibraryBig size={13} aria-hidden="true" />Add to Library</Button>}
    </div>
    {choosing && loadingContexts ? <Skeleton variant="form" rows={1} className="mt-2 w-full" /> : choosing && <div className="mt-2 w-full max-w-xs space-y-2 rounded-xl border border-border bg-surface p-3">
      <Select aria-label={`Learning context for ${file.filename}`} value={context} onChange={event => setContext(event.target.value)} disabled={busy}>
        <option value="">Choose learning context</option>{contexts.map(item => <option key={item.context_id} value={item.context_id}>{item.name}</option>)}
      </Select>
      <div className="flex flex-wrap gap-2"><Input className="min-w-32 flex-1" aria-label={`New learning context for ${file.filename}`} placeholder="Or create a learning context" value={newContext} maxLength={100} disabled={busy} onChange={event => setNewContext(event.target.value)} /><Button size="sm" variant="secondary" disabled={busy || !newContext.trim()} loading={busy} onClick={() => void addContext()}>Create context</Button></div>
      <div className="flex flex-wrap gap-2"><Button size="sm" disabled={!context || busy} loading={busy} onClick={() => void save()}>Add extracted content</Button><Button size="sm" variant="ghost" disabled={busy} onClick={() => setChoosing(false)}>Not now</Button></div>
    </div>}
    {error && <p className="mt-1 max-w-xs text-xs text-danger" role="alert">{error}</p>}
    {opened && <ChatAttachmentPreview filename={file.filename} load={loadOriginal} onClose={() => setOpened(false)} />}
  </div>;
}
