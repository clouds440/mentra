import { materialWarningMessage } from '../../services/userError';
import { Skeleton } from '../ui/Skeleton';
import { ApiError } from '../../services/api';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Image as ImageIcon, Download, CheckCircle2 } from 'lucide-react';
import { getChatAttachment, getChatAttachmentSource, saveChatAttachment } from '../../services/chatAttachments';
import type { AttachmentDetail, ChatAttachment } from '../../services/chatAttachments';
import { createContext, listContexts } from '../../services/rag';
import type { LearningContext } from '../../types/rag';
import { Button, Input, Select } from '../ui';

export function ChatAttachmentCard({ file, conversationId }: { file: ChatAttachment; conversationId: string }) {
  const [loadingContexts, setLoadingContexts] = useState(false);
  const [detail, setDetail] = useState<AttachmentDetail>();
  const [choosing, setChoosing] = useState(false), [busy, setBusy] = useState(false);
  const [contexts, setContexts] = useState<LearningContext[]>([]), [context, setContext] = useState('');
  const [error, setError] = useState<string>();
  const [newContext, setNewContext] = useState('');
  const [preview, setPreview] = useState<string>();
  const card = useRef<HTMLDivElement>(null);
  const isImage = /\.(png|jpe?g|gif|webp)$/i.test(file.filename);
  useEffect(() => {
    if (!isImage || !card.current) return;
    const controller = new AbortController(); let url: string | undefined;
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      void getChatAttachmentSource(file.id, conversationId, controller.signal).then(blob => {
        if (controller.signal.aborted || !['image/png','image/jpeg','image/gif','image/webp'].includes(blob.type)) return;
        url = URL.createObjectURL(blob); setPreview(url);
      }).catch(() => { /* The download and file card remain available. */ });
    }, {rootMargin:'100px'});
    observer.observe(card.current);
    return () => { observer.disconnect(); controller.abort(); if (url) URL.revokeObjectURL(url); setPreview(undefined); };
  }, [isImage, file.id, conversationId]);
  async function download() {
    action.current?.abort(); const controller = new AbortController(); action.current = controller;
    setBusy(true); setError(undefined);
    try {
      const blob = await getChatAttachmentSource(file.id, conversationId, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob), link = document.createElement('a');
      link.href = url; link.download = file.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'This file couldn’t be downloaded.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  const action = useRef<AbortController | null>(null);
  useEffect(() => () => action.current?.abort(), [file.id, conversationId]);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>, retries = 0;
    async function refresh() {
      try {
        const value = await getChatAttachment(file.id, conversationId, controller.signal);
        if (controller.signal.aborted) return;
        setDetail(value);
        if (!value.ready && !value.error && retries++ < 80) timer = setTimeout(() => void refresh(), 2000);
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof ApiError ? e.message : 'File unavailable.');
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
  return <div ref={card} className="mt-3 w-full max-w-md overflow-hidden rounded-2xl border border-border bg-surface p-4 text-sm shadow-sm shadow-shadow/5" aria-label={`Attachment ${file.filename}`}>
    {preview && <img src={preview} alt={file.filename} className="mb-4 max-h-64 w-full rounded-xl bg-background object-contain" />}
    <div className="flex items-start gap-3"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-border bg-background text-accent">{isImage ? <ImageIcon aria-hidden="true" size={20} /> : <FileText aria-hidden="true" size={20} />}</span><div className="min-w-0 flex-1"><p className="break-words font-medium text-heading">{file.filename}</p><p className="mt-1 text-xs text-subtle">{isImage ? 'Image' : 'Document'} · {file.size_bytes < 1024 * 1024 ? `${Math.max(1, Math.round(file.size_bytes / 1024))} KB` : `${(file.size_bytes / (1024 * 1024)).toFixed(1)} MB`} · Saved in this chat</p></div><Button aria-label={`Download ${file.filename}`} title="Download original" size="sm" variant="ghost" disabled={busy} onClick={() => void download()}><Download size={16} /></Button></div>
    {!detail && !error && <Skeleton variant="text" rows={2} className="mt-3" />}
    <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">{detail?.ready && <CheckCircle2 size={13} aria-hidden="true" />}{detail?.ready ? 'Ready to discuss' : detail?.error ? 'Could not read this file' : 'Reading this file'}</p>
    {detail?.warnings.map((warning, index) => <p key={index} className="mt-1 text-xs text-muted">{materialWarningMessage(warning)}</p>)}
    {detail?.library_result ? <Link className="mt-2 inline-block text-accent underline" to={`/library/${detail.library_result.document_id}`}>View in Library · processing status</Link>
      : choosing && loadingContexts ? <Skeleton variant="form" rows={1} className="mt-3" /> : choosing ? <div className="mt-2 space-y-2">
        <Select aria-label={`Learning context for ${file.filename}`} value={context} onChange={event => setContext(event.target.value)} disabled={busy}>
          <option value="">Choose learning context</option>{contexts.map(item => <option key={item.context_id} value={item.context_id}>{item.name}</option>)}
        </Select>
        <div className="flex flex-wrap gap-2"><Input className="min-w-32 flex-1" aria-label={`New learning context for ${file.filename}`} placeholder="Or create a learning context" value={newContext} maxLength={100} disabled={busy} onChange={event => setNewContext(event.target.value)} /><Button size="sm" variant="secondary" disabled={busy || !newContext.trim()} loading={busy} onClick={() => void addContext()}>Create context</Button></div>
        <div className="flex gap-2"><Button size="sm" disabled={!context || busy} loading={busy} onClick={() => void save()}>{'Add extracted content'}</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setChoosing(false)}>Not now</Button></div>
      </div> : <Button className="mt-2" size="sm" variant="ghost" disabled={!detail?.ready} onClick={() => void choose()}>Add to Library</Button>}
    {(error || detail?.error) && <p className="mt-2 text-xs text-danger" role="alert">{error || 'This file could not be read.'}</p>}
  </div>;
}
