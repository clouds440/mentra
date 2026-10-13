import { useEffect, useRef, useState } from 'react';
import { Dialog } from '../ui/Dialog';
import { Download, FileText, X } from 'lucide-react';
import { Button } from '../ui';
import { Spinner } from '../ui/Spinner';
import { ApiError } from '../../services/api';

export interface AttachmentOriginal { blob: Blob; url: string; image: boolean; text?: string; truncated: boolean }

export function ChatAttachmentPreview({ filename, load, onClose }: {
  filename: string; load: () => Promise<AttachmentOriginal>; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [original, setOriginal] = useState<AttachmentOriginal>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;

    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    void load().then(value => { if (active) setOriginal(value); })
      .catch(reason => { if (active) setError(reason instanceof ApiError ? reason.message : 'Couldn’t open this file. Try again.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [load, retry]);
  async function download() {
    setDownloading(true); setError('');
    try {
      const file = await load();
      if (!mounted.current) return;
      setOriginal(file);
      const anchor = document.createElement('a');
      anchor.href = file.url; anchor.download = filename; anchor.click();
    } catch (reason) { if (mounted.current) setError(reason instanceof ApiError ? reason.message : 'Couldn’t download this file. Try again.'); }
    finally { if (mounted.current) setDownloading(false); }
  }
  return <Dialog open ref={dialog} aria-label={`Preview ${filename}`} onDismiss={onClose}
    onClick={event => {
      if (event.target !== event.currentTarget) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.current?.close();
    }} className="m-auto max-h-[90dvh] w-[calc(100%-1.5rem)] max-w-5xl overflow-hidden rounded-2xl border border-border-strong bg-popover p-0 text-foreground shadow-overlay">
    <header className="flex items-center justify-between gap-3 border-b border-border px-3 py-2">
      <h2 className="min-w-0 truncate text-sm font-medium text-heading">{filename}</h2>
      <div className="flex shrink-0 items-center gap-1">
        <Button size="sm" variant="ghost" className="w-9 !px-0" aria-label={`Download ${filename}`} title="Download original" disabled={downloading} onClick={() => void download()}><Download size={17} aria-hidden="true" /></Button>
        <Button size="sm" variant="ghost" className="w-9 !px-0" aria-label="Close file preview" title="Close" autoFocus onClick={() => dialog.current?.close()}><X size={18} aria-hidden="true" /></Button>
      </div>
    </header>
    <div className="max-h-[calc(90dvh-3.5rem)] overflow-auto overscroll-contain p-3 sm:p-4">
      {loading && <div className="grid min-h-40 place-items-center" role="status" aria-label="Opening file"><Spinner className="h-5 w-5" /></div>}
      {error && <div className="space-y-3 p-3"><p role="alert" className="text-sm text-danger">{error}</p><Button size="sm" variant="secondary" onClick={() => setRetry(value => value+1)}>Try again</Button></div>}
      {original?.image && <img src={original.url} alt={filename} className="mx-auto block max-h-[74dvh] max-w-full object-contain" onError={() => setError('Couldn’t display this image. You can download the original.')} />}
      {original?.blob.type === 'application/pdf' && <iframe title={`PDF preview ${filename}`} src={original.url} className="h-[72dvh] w-full rounded-lg border-0" />}
      {original?.text !== undefined && <><pre className="whitespace-pre-wrap break-words text-sm leading-6">{original.text}</pre>{original.truncated && <p className="mt-3 text-xs text-muted">Showing the first 256 KB. Download the original for the complete file.</p>}</>}
      {original && !original.image && original.text === undefined && original.blob.type !== 'application/pdf' && <div className="flex min-h-48 flex-col items-center justify-center gap-3 text-center text-muted"><FileText size={36} aria-hidden="true" /><p className="max-w-sm text-sm">Download the original to open this file in its document application.</p></div>}
    </div>
  </Dialog>;
}
