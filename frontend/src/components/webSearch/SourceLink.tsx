import { ExternalLink, Globe } from 'lucide-react';
import { useContext, useEffect, useState, type AnchorHTMLAttributes } from 'react';
import { apiRequest } from '../../services/api';
import { buttonStyles } from '../ui';
import { PanelEntryScope, PanelResourceScope, PanelTabScope, useSidePanelActions } from '../workspace/sidePanelState';
import { openSourcesInMentra } from './sourcePreference';

// Frame only public HTTPS hosts, with no credentials, custom ports or app routes.
function previewUrl(href: string) {
  try {
    const url = new URL(href);
    const host = url.hostname.replace(/\.$/, '');
    if (url.protocol === 'https:' && url.origin !== location.origin && !url.port && !url.username && !url.password
        && /^(?:[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?\.)+[a-z]{2,}$/i.test(host)
        && !/(?:^|\.)(?:localhost|local|internal|test|invalid|example|onion|lan|corp|home\.arpa)$/i.test(host)) return url;
  } catch { /* Relative links stay in their normal navigation path. */ }
  return undefined;
}

interface PreviewResult { status: 'available' | 'blocked' | 'unavailable'; url?: string }

interface ReaderResult { url: string; blocks: string[]; links: { url: string; title: string }[] }

const readerHistory = new WeakMap<object, { reading: boolean; reader?: ReaderResult | null }>();

export function WebSourcePreview({ href, title }: { href: string; title: string }) {
  const url = new URL(href);
  const entry = useContext(PanelEntryScope);
  const previous = entry && readerHistory.get(entry);
  const [reading, setReading] = useState(previous?.reading ?? false);
  const [reader, setReader] = useState<ReaderResult | null | undefined>(previous?.reader);
  useEffect(() => {
    if (entry) readerHistory.set(entry, { reading, reader });
  }, [entry, reading, reader]);
  useEffect(() => {
    if (!reading || reader !== undefined) return;
    const controller = new AbortController();
    void apiRequest<ReaderResult | null>('/api/v1/web/reader', {
      method: 'POST', body: JSON.stringify({ url: href }), signal: controller.signal,
    }).then(value => { if (!controller.signal.aborted) setReader(value); })
      .catch(() => { if (!controller.signal.aborted) setReader(null); });
    return () => controller.abort();
  }, [href, reading, reader]);
  const [result, setResult] = useState<PreviewResult>();
  useEffect(() => {
    if (reading || result !== undefined) return;
    const controller = new AbortController();
    const requestUrl = new URL(href);
    requestUrl.hash = '';
    const timer = setTimeout(() => {
      setResult({ status: 'unavailable' });
      controller.abort();
    }, 6000);
    void apiRequest<PreviewResult>('/api/v1/web/preview', {
      method: 'POST', body: JSON.stringify({ url: requestUrl.href }), signal: controller.signal,
    }).then(value => {
      if (!controller.signal.aborted) setResult(value);
    }).catch(() => {
      if (!controller.signal.aborted) setResult({ status: 'unavailable' });
    }).finally(() => clearTimeout(timer));
    return () => { clearTimeout(timer); controller.abort(); };
  }, [href, reading, result]);
  const frame = result?.status === 'available' && result.url ? previewUrl(result.url) : undefined;
  if (frame && !frame.hash) frame.hash = url.hash;
  return <div className="workspace-web-preview">
    <header className="workspace-web-toolbar">
      <button type="button" aria-pressed={reading} title={reading ? 'Return to website preview' : 'Open Reader to select and quote text'} className={buttonStyles({ size: 'sm', variant: reading ? 'secondary' : 'ghost' })} onClick={() => setReading(value => !value)}>Reader</button>
      <span className="min-w-0 flex-1 truncate text-xs text-muted" title={url.hostname}>{url.hostname}</span>
      <a href={url.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer"
        className={buttonStyles({ size: 'sm', variant: 'ghost' })}>Open in browser <ExternalLink size={14} aria-hidden="true" /></a>
    </header>
    {reading ? reader ? <div data-reader-url={reader.url} className="space-y-3 p-4 text-sm leading-relaxed">
      {reader.blocks.map((block, index) => <p key={index} dir="auto" className="break-words">{block}</p>)}
      {!!reader.links.length && <ul className="space-y-2 border-t border-border pt-3">{reader.links.map(link => <li key={link.url}>
        <SourceLink href={link.url} sourceTitle={link.title} className="text-accent hover:underline">{link.title}</SourceLink>
      </li>)}</ul>}
    </div> : <div className="workspace-web-status" role="status">{reader === null ? <>Readable text is unavailable for this page.
      <button type="button" className={buttonStyles({ size: 'sm', variant: 'ghost' })} onClick={() => setReader(undefined)}>Retry Reader</button></> : 'Loading readable text…'}</div>
    : frame ? <iframe src={frame.href} title={title} sandbox="allow-scripts" referrerPolicy="no-referrer"
      allow="camera 'none'; microphone 'none'; geolocation 'none'; payment 'none'; clipboard-read 'none'; clipboard-write 'none'"
      {...{ credentialless: '' }} /> : <div className="workspace-web-status" role="status">
      <Globe size={24} strokeWidth={1.5} aria-hidden="true" />
      <p className="text-sm font-medium text-heading">{!result ? 'Checking preview…' : result.status === 'blocked' ? 'This publisher restricts embedded previews' : 'Preview unavailable'}</p>
      {result && <p className="text-xs text-muted">Try Reader for selectable text, or open the original page in your browser.</p>}
    </div>}
  </div>;
}

interface SourceLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href' | 'onClick'> {
  href: string;
  sourceTitle?: string;
  onPreview?: () => void;
}

/** A real link preserves the browser's modifier, middle-click and context-menu actions. */
export function SourceLink({ href, sourceTitle, onPreview, children, ...props }: SourceLinkProps) {
  const panel = useSidePanelActions();
  const parentId = useContext(PanelTabScope);
  const resource = useContext(PanelResourceScope);
  const external = /^https?:\/\//i.test(href);
  return <a {...props} href={href} target={external ? '_blank' : props.target} rel="noopener noreferrer" referrerPolicy="no-referrer"
    onClick={event => {
      if (!panel || props.download != null || !openSourcesInMentra() || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const url = previewUrl(href);
      if (!url) return;
      event.preventDefault();
      onPreview?.();
      const title = (sourceTitle?.trim() || event.currentTarget.textContent?.trim() || url.hostname).slice(0, 300);
      panel.open({ title, parentId, inPlace: !!resource, resource: { kind: 'web', title, url: url.href },
        icon: <Globe size={14} aria-hidden="true" />, content: <WebSourcePreview href={url.href} title={title} /> });
    }}>{children}</a>;
}

export function SourceMarkdownLink({ href, children }: Pick<SourceLinkProps, 'children'> & { href?: string }) {
  return href ? <SourceLink href={href}>{children}</SourceLink> : <span>{children}</span>;
}
