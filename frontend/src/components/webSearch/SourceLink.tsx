import { ArrowLeft, ExternalLink, Globe } from 'lucide-react';
import { useContext, useEffect, useState, type AnchorHTMLAttributes } from 'react';
import { apiRequest } from '../../services/api';
import { buttonStyles, IconButton } from '../ui';
import { PanelTabScope, useSidePanelActions } from '../workspace/sidePanelState';
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

function WebSourcePreview({ url, title }: { url: URL; title: string }) {
  const panel = useSidePanelActions();
  const tab = useContext(PanelTabScope);
  const [result, setResult] = useState<PreviewResult>();
  useEffect(() => {
    const controller = new AbortController();
    const requestUrl = new URL(url);
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
  }, [url]);
  const frame = result?.status === 'available' && result.url ? previewUrl(result.url) : undefined;
  if (frame && !frame.hash) frame.hash = url.hash;
  return <div className="workspace-web-preview">
    <header className="workspace-web-toolbar">
      {panel && tab && <IconButton size="sm" aria-label="Back" title="Back to previous panel view" onClick={() => panel.back(tab)}><ArrowLeft size={16} aria-hidden="true" /></IconButton>}
      <span className="min-w-0 flex-1 truncate text-xs text-muted" title={url.hostname}>{url.hostname}</span>
      <a href={url.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer"
        className={buttonStyles({ size: 'sm', variant: 'ghost' })}>Open in browser <ExternalLink size={14} aria-hidden="true" /></a>
    </header>
    {frame ? <iframe src={frame.href} title={title} sandbox="allow-scripts" referrerPolicy="no-referrer"
      allow="camera 'none'; microphone 'none'; geolocation 'none'; payment 'none'; clipboard-read 'none'; clipboard-write 'none'"
      {...{ credentialless: '' }} /> : <div className="workspace-web-status" role="status">
      <Globe size={24} strokeWidth={1.5} aria-hidden="true" />
      <p className="text-sm font-medium text-heading">{!result ? 'Checking preview…' : result.status === 'blocked' ? 'This publisher restricts embedded previews' : 'Preview unavailable'}</p>
      {result && <p className="text-xs text-muted">Use Open in browser to visit the original page.</p>}
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
  const external = /^https?:\/\//i.test(href);
  return <a {...props} href={href} target={external ? '_blank' : props.target} rel="noopener noreferrer" referrerPolicy="no-referrer"
    onClick={event => {
      if (!panel || props.download != null || !openSourcesInMentra() || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const url = previewUrl(href);
      if (!url) return;
      event.preventDefault();
      onPreview?.();
      const title = sourceTitle?.trim() || event.currentTarget.textContent?.trim() || url.hostname;
      panel.open({ title, parentId, icon: <Globe size={14} aria-hidden="true" />, content: <WebSourcePreview url={url} title={title} /> });
    }}>{children}</a>;
}

export function SourceMarkdownLink({ href, children }: Pick<SourceLinkProps, 'children'> & { href?: string }) {
  return href ? <SourceLink href={href}>{children}</SourceLink> : <span>{children}</span>;
}
