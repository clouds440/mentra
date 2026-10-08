import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button, Spinner } from '../ui';
import { downloadSource, getSourceChunks, materialError } from '../../services/rag';
import type { SourceReference, SourceChunk } from '../../types/rag';

export function sourceLocation(source: Pick<SourceReference, 'spans' | 'heading_path'>) {
  return source.spans.map(s => s.page ? `Page ${s.page}` : s.slide ? `Slide ${s.slide}` : `Section ${s.block + 1}`).join(', ') || source.heading_path.join(' / ');
}

export function SourceViewer({ source, filename, includeArchived = false, onClose }: { source: SourceReference; filename?: string; includeArchived?: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [chunks, setChunks] = useState<SourceChunk[]>([]); const [error, setError] = useState('');
  const [loading, setLoading] = useState(true); const [downloadBusy, setDownloadBusy] = useState(false);
  const [more, setMore] = useState(false); const [loadingMore, setLoadingMore] = useState(false);
  const [url, setUrl] = useState(''); const [media, setMedia] = useState(''); const controllerRef = useRef<AbortController>();
  useEffect(() => {
    dialog.current?.showModal();
    const controller = new AbortController(); controllerRef.current = controller;
    setLoading(true); setChunks([]); setError('');
    void getSourceChunks(source.document_id, source.version_id, includeArchived, controller.signal, 0, source.generation_id || undefined).then(items => { if (!controller.signal.aborted) { setChunks(items); setMore(items.length === 100); } })
      .catch(e => { if (!controller.signal.aborted) setError(materialError(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); };
  }, [source.document_id, source.version_id, source.generation_id, includeArchived]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  async function loadMore() {
    setLoadingMore(true); setError('');
    try {
      const items = await getSourceChunks(source.document_id, source.version_id, includeArchived, controllerRef.current?.signal, chunks.length, source.generation_id || undefined);
      if (!controllerRef.current?.signal.aborted) { setChunks(previous => [...previous, ...items]); setMore(items.length === 100); }
    } catch (e) { if (!controllerRef.current?.signal.aborted) setError(materialError(e)); }
    finally { if (!controllerRef.current?.signal.aborted) setLoadingMore(false); }
  }
  async function download() {
    setDownloadBusy(true); setError('');
    try {
      const blob = await downloadSource(source.document_id, source.version_id, includeArchived, controllerRef.current?.signal);
      if (controllerRef.current?.signal.aborted) return;
      const objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); setMedia(blob.type);
      const a = document.createElement('a'); a.href = objectUrl; a.download = filename ?? source.title; a.click();
    } catch (e) { if (!controllerRef.current?.signal.aborted) setError(materialError(e)); }
    finally { if (!controllerRef.current?.signal.aborted) setDownloadBusy(false); }
  }
  return createPortal(<dialog ref={dialog} onClose={onClose} aria-label={`Source: ${source.title}`} className="m-auto max-h-[85dvh] w-[calc(100%-2rem)] max-w-3xl overflow-auto rounded-2xl border border-border bg-surface p-5 text-foreground backdrop:bg-black/40">
    <div className="flex items-start justify-between gap-4"><div><h2 className="text-lg font-medium">{source.title}</h2><p className="text-sm text-muted">{sourceLocation(source)}</p></div><Button variant="secondary" onClick={() => dialog.current?.close()}>Close source</Button></div>
    {source.warnings.map(w => <p key={w} className="mt-3 text-sm text-muted">{w}</p>)}
    {source.excerpt && <blockquote className="my-4 whitespace-pre-wrap rounded-xl border border-accent/30 bg-input p-4 text-sm">{source.excerpt}</blockquote>}
    {loading && <Spinner />}{error && <p role="alert" className="my-3 text-sm text-danger">{error}</p>}
    <Button className="my-4" variant="secondary" disabled={downloadBusy} onClick={() => void download()}>{downloadBusy ? 'Opening original…' : 'Download original'}</Button>
    {url && media.startsWith('image/') && <img src={url} alt="Original study material" className="max-w-full" />}
    {url && media === 'application/pdf' && <iframe title="Original PDF" src={url} className="h-96 w-full rounded-xl border border-border" />}
    <div className="space-y-4">{chunks.map(chunk => <section key={chunk.id} className="rounded-xl border border-border p-4"><p className="mb-2 text-xs text-subtle">{sourceLocation(chunk)}</p><pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6">{chunk.content}</pre></section>)}</div>
    {more && <Button className="mt-4" variant="secondary" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? 'Loading passages…' : 'Load more passages'}</Button>}
  </dialog>, document.body);
}
