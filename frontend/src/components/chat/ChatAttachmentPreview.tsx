import { useEffect, useState } from 'react';
import { getChatAttachmentSource } from '../../services/chatAttachments';
import { fileLanguage } from '../../lib/codeLanguages';
import { Download, FileText } from 'lucide-react';
import { Button } from '../ui';
import { Spinner } from '../ui/Spinner';
import { ApiError } from '../../services/api';

export interface AttachmentOriginal { blob: Blob; url: string; image: boolean; text?: string; truncated: boolean }

export async function readAttachmentOriginal(blob: Blob, filename: string, signal: AbortSignal): Promise<AttachmentOriginal> {
  const image = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(blob.type);
  const textual = !image && blob.type !== 'application/pdf' && !blob.type.includes('officedocument')
    && (!!fileLanguage(filename) || blob.type.startsWith('text/') || ['application/json', 'application/xml', 'application/yaml'].includes(blob.type));
  const limit = 256 * 1024;
  const text = textual ? new TextDecoder().decode(await blob.slice(0, limit).arrayBuffer(), { stream: blob.size > limit }) : undefined;
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  return { blob, url: URL.createObjectURL(blob), image, text, truncated: textual && blob.size > limit };
}

export function ChatAttachmentPreview({ filename, fileId, conversationId, cached }: {
  filename: string; fileId: string; conversationId: string; cached?: Blob;
}) {
  const [original, setOriginal] = useState<AttachmentOriginal>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let url: string | undefined;
    setLoading(true); setError(''); setOriginal(undefined);
    void (cached ? Promise.resolve(cached) : getChatAttachmentSource(fileId, conversationId, controller.signal))
      .then(blob => readAttachmentOriginal(blob, filename, controller.signal))
      .then(value => {
        if (controller.signal.aborted) URL.revokeObjectURL(value.url);
        else { url = value.url; setOriginal(value); }
      })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Couldn’t open this file. Try again.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [fileId, conversationId, filename, cached, retry]);
  return <>
    <header className="flex items-center justify-between gap-3 border-b border-border px-3 py-2">
      <h2 className="min-w-0 truncate text-sm font-medium text-heading">{filename}</h2>
      <div className="flex shrink-0 items-center gap-1">
        {original && <a className="icon-control grid h-8 w-8 place-items-center rounded-control text-muted hover:bg-hover focus-visible:ring-2 focus-visible:ring-accent" aria-label={'Download ' + filename} title="Download original" href={original.url} download={filename}><Download size={17} aria-hidden="true" /></a>}

      </div>
    </header>
    <div className="p-3 sm:p-4">
      {loading && <div className="grid min-h-40 place-items-center" role="status" aria-label="Opening file"><Spinner className="h-5 w-5" /></div>}
      {error && <div className="space-y-3 p-3"><p role="alert" className="text-sm text-danger">{error}</p><Button size="sm" variant="secondary" onClick={() => setRetry(value => value+1)}>Try again</Button></div>}
      {original?.image && <img src={original.url} alt={filename} className="mx-auto block max-h-[74dvh] max-w-full object-contain" onError={() => setError('Couldn’t display this image. You can download the original.')} />}
      {original?.blob.type === 'application/pdf' && <iframe title={`PDF preview ${filename}`} src={original.url} className="h-[72dvh] w-full rounded-lg border-0" />}
      {original?.text !== undefined && <><pre className="whitespace-pre-wrap break-words text-sm leading-6">{original.text}</pre>{original.truncated && <p className="mt-3 text-xs text-muted">Showing the first 256 KB. Download the original for the complete file.</p>}</>}
      {original && !original.image && original.text === undefined && original.blob.type !== 'application/pdf' && <div className="flex min-h-48 flex-col items-center justify-center gap-3 text-center text-muted"><FileText size={36} aria-hidden="true" /><p className="max-w-sm text-sm">Download the original to open this file in its document application.</p></div>}
    </div>
  </>;
}
