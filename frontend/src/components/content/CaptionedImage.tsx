import { memo, useState } from 'react';
import { Button, Dialog } from '../ui';
import { publicImageUrl } from '../../lib/imageUrls';

export const CaptionedImage = memo(function CaptionedImage({ src, alt, label, source }: {src: string; alt: string; label: string; source?: string}) {
  const url = publicImageUrl(src, true); const sourceUrl = source ? publicImageUrl(source, true) : null;
  const [failed, setFailed] = useState(false); const [expanded, setExpanded] = useState(false);
  const caption = (label || alt || 'Image').slice(0, 1000);
  const image = (fullscreen = false) => url && !failed ? <img src={url} alt={alt || caption} loading={fullscreen ? 'eager' : 'lazy'} decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)} className={fullscreen ? 'max-h-full max-w-full object-contain' : 'max-h-[32rem] w-full object-contain'} /> : <span role="status" className="flex min-h-40 items-center justify-center p-4 text-sm text-muted">Image unavailable</span>;
  return <figure className="markdown-image my-4 overflow-hidden rounded-panel border border-border bg-card">
    {url && !failed ? <button type="button" aria-label={`Expand image: ${caption}`} className="block w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent" onClick={() => setExpanded(true)}>{image()}</button> : image()}
    <figcaption className="border-t border-border bg-surface px-3 py-2 text-sm leading-6 text-muted">{caption}{sourceUrl && <> · <a href={sourceUrl} rel="noopener noreferrer" target="_blank">Source</a></>}</figcaption>
    {expanded && <Dialog open className="visual-fullscreen" aria-label={`Expanded image: ${caption}`} onDismiss={() => setExpanded(false)}><div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-2"><span className="text-sm text-heading">Image</span><Button variant="ghost" onClick={() => setExpanded(false)}>Close</Button></div><div className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-3">{image(true)}</div><p className="shrink-0 border-t border-border bg-surface px-4 py-3 text-sm text-muted">{caption}</p></Dialog>}
  </figure>;
});
