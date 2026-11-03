import { Dialog } from '../ui/Dialog';
import { SourceDiagrams } from './SourceDiagrams';
import { Skeleton } from '../ui/Skeleton';
import { useEffect, useMemo, useRef, useState } from 'react';

import { Download, FileText, ArrowDown } from 'lucide-react';
import { Button } from '../ui';
import { CodeBlock } from '../content/CodeBlock';
import { MarkdownContent } from '../content/MarkdownContent';
import { fileLanguage } from '../../lib/codeLanguages';
import { groupPassages, isMarkdown, passageLanguage } from './sourcePresentation';
import { downloadSource, getSourceChunk, getSourceChunks, materialError } from '../../services/rag';
import type { SourceReference, SourceChunk } from '../../types/rag';

export function sourceLocation(source: Pick<SourceReference, 'spans' | 'heading_path'>) {
  return [...new Set(source.spans.map(s => s.page ? `Page ${s.page}` : s.slide ? `Slide ${s.slide}` : `Section ${s.block + 1}`))].join(', ') || source.heading_path.join(' / ');
}
interface OriginalFile { blob: Blob; url: string; media: string; text?: string; truncated: boolean }
export interface SourceStatus { state: 'processing' | 'ready' | 'failed' | 'unavailable'; error?: string | null }

export function SourceViewer({ source, filename, includeArchived = false, status, onRefresh, onClose }: { source: SourceReference; filename?: string; includeArchived?: boolean; status?: SourceStatus; onRefresh?: () => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [chunks, setChunks] = useState<SourceChunk[]>([]);
  const [citedChunk, setCitedChunk] = useState<SourceChunk>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [more, setMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [view, setView] = useState<'extracted' | 'original'>('extracted');
  const [original, setOriginal] = useState<OriginalFile>();
  const [opening, setOpening] = useState(false);
  const [reload, setReload] = useState(0);
  const controllerRef = useRef<AbortController>();
  const originalRequest = useRef<Promise<OriginalFile>>();
  const displayFilename = filename ?? source.filename ?? chunks[0]?.filename;
  const passages = useMemo(() => [...(citedChunk ? [citedChunk] : []), ...groupPassages(chunks.filter(chunk => chunk.id !== citedChunk?.id))], [chunks, citedChunk]);
  useEffect(() => {

    const controller = new AbortController(); controllerRef.current = controller;
    setOpening(false); setDownloadBusy(false);
    setLoading(true); setLoadingMore(false); setMore(false); setChunks([]); setCitedChunk(undefined); setError(''); setOriginal(undefined); setView('extracted'); originalRequest.current = undefined;
    async function load() {
      if (!source.generation_id && status && status.state !== 'ready') return;
      if (source.chunk_id) {
        const chunk = await getSourceChunk(source.chunk_id, includeArchived, controller.signal);
        if (chunk.document_id !== source.document_id || chunk.version_id !== source.version_id || source.generation_id && chunk.generation_id !== source.generation_id) throw new Error('Source identity changed');
        if (!controller.signal.aborted) { setCitedChunk({ ...chunk, media_type: source.media_type ?? chunk.media_type }); setMore(true); }
      } else {
        const items = await getSourceChunks(source.document_id, source.version_id, includeArchived, controller.signal, 0, source.generation_id || undefined);
        if (!controller.signal.aborted) { setChunks(items); setMore(items.length === 100); }
      }
    }
    void load()
      .catch(e => { if (!controller.signal.aborted) setError(materialError(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [source.document_id, source.version_id, source.generation_id, source.chunk_id, includeArchived, status?.state, reload]);
  useEffect(() => () => { if (original?.url) URL.revokeObjectURL(original.url); }, [original?.url]);
  async function loadMore() {
    if (loadingMore) return;
    const controller = controllerRef.current;
    setLoadingMore(true); setError('');
    try {
      const items = await getSourceChunks(source.document_id, source.version_id, includeArchived, controller?.signal, chunks.length, source.generation_id || undefined);
      if (!controller?.signal.aborted) { setChunks(previous => [...previous, ...items]); setMore(items.length === 100); }
    } catch (e) { if (!controller?.signal.aborted) setError(materialError(e)); }
    finally { if (!controller?.signal.aborted) setLoadingMore(false); }
  }
  async function originalFile() {
    if (original) return original;
    if (originalRequest.current) return originalRequest.current;
    const controller = controllerRef.current;
    const request = downloadSource(source.document_id, source.version_id, includeArchived, controller?.signal).then(async blob => {
      const media = blob.type;
      const binary = media.startsWith('image/') || media === 'application/pdf' || media.includes('officedocument');
      const textual = !binary && (!!fileLanguage(displayFilename) || media.startsWith('text/') || ['application/json', 'application/xml', 'application/yaml', 'application/toml', 'application/sql'].includes(media));
      const limit = 256 * 1024;
      const text = textual ? new TextDecoder().decode(await blob.slice(0, limit).arrayBuffer(), { stream: blob.size > limit }) : undefined;
      if (controller?.signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const file = { blob, url: URL.createObjectURL(blob), media, text, truncated: textual && blob.size > limit };
      setOriginal(file); return file;
    });
    originalRequest.current = request;
    try { return await request; } finally { if (originalRequest.current === request) originalRequest.current = undefined; }
  }
  async function openOriginal() {
    const controller = controllerRef.current;
    setView('original'); setOpening(true); setError('');
    try { await originalFile(); } catch (e) { if (!controller?.signal.aborted) setError(materialError(e)); }
    finally { if (!controller?.signal.aborted) setOpening(false); }
  }
  async function download() {
    const controller = controllerRef.current;
    setDownloadBusy(true); setError('');
    try {
      const file = await originalFile();
      if (controller?.signal.aborted) return;
      const anchor = document.createElement('a'); anchor.href = file.url; anchor.download = displayFilename ?? source.title; anchor.click();
    } catch (e) { if (!controller?.signal.aborted) setError(materialError(e)); }
    finally { if (!controller?.signal.aborted) setDownloadBusy(false); }
  }
  return <Dialog closeLabel="Close source" open ref={dialog} onDismiss={onClose} aria-label={`Source: ${source.title}`} layout="viewer" className="source-dialog max-w-4xl">
    <header className="source-header">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><p className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent"><FileText size={13} aria-hidden="true" />Library source</p><h2 className="truncate text-xl font-semibold tracking-tight text-heading">{source.title}</h2><p className="mt-1 truncate text-xs text-muted" title={displayFilename}>{displayFilename ?? sourceLocation(source) ?? 'Study material'}</p></div>

      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><span className="text-xs text-muted">{sourceLocation(source) || 'Source content'}{chunks.length > 0 ? ` · ${chunks.length}${more ? '+' : ''} ${chunks.length === 1 ? 'passage' : 'passages'}` : ''}</span><Button size="sm" variant="secondary" disabled={downloadBusy} onClick={() => void download()}><Download size={14} aria-hidden="true" />{downloadBusy ? 'Opening original…' : 'Download original'}</Button></div>
      <nav className="source-tabs" aria-label="Source view"><button type="button" aria-pressed={view === 'extracted'} onClick={() => setView('extracted')}>Extracted content</button><button type="button" aria-pressed={view === 'original'} onClick={() => void openOriginal()}>Original file</button></nav>
    </header>
    <div className="source-reader">
      {error && <p role="alert" className="mb-4 text-sm text-danger">{error}</p>}
      {view === 'extracted' ? <>
        {status?.state === 'processing' && <p role="status" className="mb-4 text-sm text-muted">Reading and indexing this source. Extracted content and notes will appear here when processing finishes. The original file is available.</p>}
        {status?.state === 'failed' && <p role="alert" className="mb-4 text-sm text-danger">{status.error || 'Source extraction did not finish.'} Your original file is preserved. Retry processing from the material page.</p>}
        {status?.state === 'ready' && status.error && <p role="alert" className="mb-4 text-sm text-muted">Latest processing attempt failed: {status.error} Showing the previously indexed content.</p>}
        {loading && <Skeleton variant="text" rows={8} className="py-6" />}
        {!loading && !error && chunks.length === 0 && !citedChunk && status?.state !== 'processing' && status?.state !== 'failed' && <p className="source-prose">{source.excerpt || (status?.state === 'ready' ? 'This source was indexed, but its extracted passages could not be loaded. Refresh the content or open the original file.' : 'No published extraction is available for this version yet. Your original file is preserved.')}</p>}
        {!loading && (error || !chunks.length && !citedChunk && status?.state !== 'processing') && <Button className="mt-4" variant="secondary" onClick={() => { onRefresh?.(); setReload(value => value + 1); }}>Refresh content</Button>}
        {passages.map(chunk => {
          const language = passageLanguage(chunk, displayFilename);
          const cited = chunk.id === source.chunk_id || chunk.spans.some(span => source.spans.some(selected => selected.block === span.block && selected.start < span.end && selected.end > span.start));
          return <section key={chunk.id} className="source-passage"><div className="mb-3 flex flex-wrap items-center gap-2 text-[10px] font-medium text-muted"><span className="uppercase tracking-wider">{sourceLocation(chunk)}</span>{cited && <span className="rounded-full bg-accent/10 px-2 py-0.5 text-accent">Cited passage</span>}{chunk.heading_path.length > 0 && <span>{chunk.heading_path.join(' / ')}</span>}</div>{isMarkdown(language) ? <MarkdownContent content={chunk.content} /> : language ? <CodeBlock code={chunk.content} language={language} /> : <div className="source-prose">{chunk.content}</div>}<SourceDiagrams visuals={chunk.visuals} archived={includeArchived} /></section>;
        })}
        {more && <Button className="mt-6" variant="secondary" disabled={loadingMore} loading={loadingMore} onClick={() => void loadMore()}><ArrowDown size={14} aria-hidden="true" />{citedChunk && !chunks.length ? 'Read full source' : 'Load more passages'}</Button>}
      </> : <>
        {opening && !original && <Skeleton variant="text" rows={8} className="py-6" />}
        {original?.text !== undefined && <><CodeBlock code={original.text} language={fileLanguage(displayFilename) ?? 'plain'} filename={displayFilename ?? undefined} />{original.truncated && <p className="mt-3 text-xs text-muted">Preview shows the first 256 KiB. Download the original for the complete file.</p>}</>}
        {original?.media.startsWith('image/') && <img src={original.url} alt="Original study material" className="mx-auto max-h-[65dvh] max-w-full rounded-xl object-contain" />}
        {original?.media === 'application/pdf' && <iframe title="Original PDF" src={`${original.url}${source.spans.find(span => span.page)?.page ? `#page=${source.spans.find(span => span.page)!.page}` : ''}`} className="h-[60dvh] w-full rounded-xl border border-border" />}
        {original && original.text === undefined && !original.media.startsWith('image/') && original.media !== 'application/pdf' && <div className="flex min-h-48 flex-col items-center justify-center gap-3 text-center text-muted"><FileText size={32} strokeWidth={1.2} aria-hidden="true" /><p className="text-sm">{displayFilename ?? 'Original file'}</p><p className="max-w-xs text-xs leading-5">Read the extracted content here, or download the original to open it in its document application.</p></div>}
      </>}
    </div>
  </Dialog>;
}
