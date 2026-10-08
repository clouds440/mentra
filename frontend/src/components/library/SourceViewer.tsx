import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, FileText, X, ArrowDown, AlertCircle } from 'lucide-react';
import { Button, Spinner } from '../ui';
import { CodeBlock } from '../content/CodeBlock';
import { MarkdownContent } from '../content/MarkdownContent';
import { fileLanguage } from '../../lib/codeLanguages';
import { groupPassages, isMarkdown, passageLanguage } from './sourcePresentation';
import { downloadSource, getSourceChunks, materialError } from '../../services/rag';
import type { SourceReference, SourceChunk } from '../../types/rag';

export function sourceLocation(source: Pick<SourceReference, 'spans' | 'heading_path'>) {
  return [...new Set(source.spans.map(s => s.page ? `Page ${s.page}` : s.slide ? `Slide ${s.slide}` : `Section ${s.block + 1}`))].join(', ') || source.heading_path.join(' / ');
}
interface OriginalFile { blob: Blob; url: string; media: string; text?: string; truncated: boolean }

export function SourceViewer({ source, filename, includeArchived = false, onClose }: { source: SourceReference; filename?: string; includeArchived?: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [chunks, setChunks] = useState<SourceChunk[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [more, setMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [view, setView] = useState<'extracted' | 'original'>('extracted');
  const [original, setOriginal] = useState<OriginalFile>();
  const [opening, setOpening] = useState(false);
  const controllerRef = useRef<AbortController>();
  const originalRequest = useRef<Promise<OriginalFile>>();
  const displayFilename = filename ?? source.filename ?? chunks[0]?.filename;
  const passages = useMemo(() => groupPassages(chunks), [chunks]);
  useEffect(() => {
    dialog.current?.showModal();
    const controller = new AbortController(); controllerRef.current = controller;
    setLoading(true); setChunks([]); setError(''); setOriginal(undefined); setView('extracted'); originalRequest.current = undefined;
    void getSourceChunks(source.document_id, source.version_id, includeArchived, controller.signal, 0, source.generation_id || undefined)
      .then(items => { if (!controller.signal.aborted) { setChunks(items); setMore(items.length === 100); } })
      .catch(e => { if (!controller.signal.aborted) setError(materialError(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [source.document_id, source.version_id, source.generation_id, includeArchived]);
  useEffect(() => () => { if (original?.url) URL.revokeObjectURL(original.url); }, [original?.url]);
  async function loadMore() {
    setLoadingMore(true); setError('');
    try {
      const items = await getSourceChunks(source.document_id, source.version_id, includeArchived, controllerRef.current?.signal, chunks.length, source.generation_id || undefined);
      if (!controllerRef.current?.signal.aborted) { setChunks(previous => [...previous, ...items]); setMore(items.length === 100); }
    } catch (e) { if (!controllerRef.current?.signal.aborted) setError(materialError(e)); }
    finally { if (!controllerRef.current?.signal.aborted) setLoadingMore(false); }
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
    setView('original'); setOpening(true); setError('');
    try { await originalFile(); } catch (e) { if (!controllerRef.current?.signal.aborted) setError(materialError(e)); }
    finally { if (!controllerRef.current?.signal.aborted) setOpening(false); }
  }
  async function download() {
    setDownloadBusy(true); setError('');
    try {
      const file = await originalFile();
      if (controllerRef.current?.signal.aborted) return;
      const anchor = document.createElement('a'); anchor.href = file.url; anchor.download = displayFilename ?? source.title; anchor.click();
    } catch (e) { if (!controllerRef.current?.signal.aborted) setError(materialError(e)); }
    finally { if (!controllerRef.current?.signal.aborted) setDownloadBusy(false); }
  }
  return createPortal(<dialog ref={dialog} onClose={onClose} aria-label={`Source: ${source.title}`} className="source-dialog m-auto max-h-[88dvh] w-[calc(100%-1.5rem)] max-w-4xl rounded-2xl border border-border-strong bg-card text-foreground shadow-2xl backdrop:bg-black/50 backdrop:backdrop-blur-sm">
    <header className="source-header">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><p className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent"><FileText size={13} aria-hidden="true" />Library source</p><h2 className="truncate text-xl font-semibold tracking-tight text-heading">{source.title}</h2><p className="mt-1 truncate text-xs text-muted" title={displayFilename}>{displayFilename ?? sourceLocation(source) ?? 'Study material'}</p></div>
        <Button variant="ghost" size="sm" className="shrink-0 !px-2" aria-label="Close source" onClick={() => dialog.current?.close()}><X size={18} aria-hidden="true" /></Button>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><span className="text-xs text-muted">{sourceLocation(source) || 'Source content'}{chunks.length > 0 ? ` · ${chunks.length}${more ? '+' : ''} ${chunks.length === 1 ? 'passage' : 'passages'}` : ''}</span><Button size="sm" variant="secondary" disabled={downloadBusy} onClick={() => void download()}><Download size={14} aria-hidden="true" />{downloadBusy ? 'Opening original…' : 'Download original'}</Button></div>
      <nav className="source-tabs" aria-label="Source view"><button type="button" aria-pressed={view === 'extracted'} onClick={() => setView('extracted')}>Extracted content</button><button type="button" aria-pressed={view === 'original'} onClick={() => void openOriginal()}>Original file</button></nav>
    </header>
    <div className="source-reader">
      {error && <p role="alert" className="mb-4 text-sm text-danger">{error}</p>}
      {view === 'extracted' ? <>
        {source.warnings.length > 0 && <details className="mb-5 rounded-xl border border-border bg-surface px-4 py-3 text-xs text-muted"><summary className="cursor-pointer"><AlertCircle size={13} className="mr-2 inline" aria-hidden="true" />Extraction notes ({source.warnings.length})</summary><ul className="mt-3 space-y-2">{source.warnings.map(w => <li key={w}>{w}</li>)}</ul></details>}
        {loading && <div className="flex min-h-40 items-center justify-center"><Spinner /></div>}
        {!loading && chunks.length === 0 && <p className="source-prose">{source.excerpt || 'No extracted passages are available for this version. Open the original file to inspect it.'}</p>}
        {passages.map(chunk => {
          const language = passageLanguage(chunk, displayFilename);
          const cited = chunk.spans.some(span => source.spans.some(selected => selected.block === span.block && selected.start < span.end && selected.end > span.start));
          return <section key={chunk.id} className="source-passage"><div className="mb-3 flex flex-wrap items-center gap-2 text-[10px] font-medium text-muted"><span className="uppercase tracking-wider">{sourceLocation(chunk)}</span>{cited && <span className="rounded-full bg-accent/10 px-2 py-0.5 text-accent">Cited passage</span>}{chunk.heading_path.length > 0 && <span>{chunk.heading_path.join(' / ')}</span>}</div>{isMarkdown(language) ? <MarkdownContent content={chunk.content} /> : language ? <CodeBlock code={chunk.content} language={language} /> : <div className="source-prose">{chunk.content}</div>}</section>;
        })}
        {more && <Button className="mt-6" variant="secondary" disabled={loadingMore} onClick={() => void loadMore()}><ArrowDown size={14} aria-hidden="true" />{loadingMore ? 'Loading passages…' : 'Load more passages'}</Button>}
      </> : <>
        {opening && !original && <div className="flex min-h-40 items-center justify-center"><Spinner /></div>}
        {original?.text !== undefined && <><CodeBlock code={original.text} language={fileLanguage(displayFilename) ?? 'plain'} filename={displayFilename ?? undefined} />{original.truncated && <p className="mt-3 text-xs text-muted">Preview shows the first 256 KiB. Download the original for the complete file.</p>}</>}
        {original?.media.startsWith('image/') && <img src={original.url} alt="Original study material" className="mx-auto max-h-[65dvh] max-w-full rounded-xl object-contain" />}
        {original?.media === 'application/pdf' && <iframe title="Original PDF" src={original.url} className="h-[60dvh] w-full rounded-xl border border-border" />}
        {original && original.text === undefined && !original.media.startsWith('image/') && original.media !== 'application/pdf' && <div className="flex min-h-48 flex-col items-center justify-center gap-3 text-center text-muted"><FileText size={32} strokeWidth={1.2} aria-hidden="true" /><p className="text-sm">{displayFilename ?? 'Original file'}</p><p className="max-w-xs text-xs leading-5">Read the extracted content here, or download the original to open it in its document application.</p></div>}
      </>}
    </div>
  </dialog>, document.body);
}
