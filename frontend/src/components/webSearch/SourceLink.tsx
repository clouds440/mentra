import { ExternalLink, Globe } from 'lucide-react';
import type { AnchorHTMLAttributes } from 'react';
import { buttonStyles } from '../ui/Button';
import { useSidePanelActions } from '../workspace/sidePanelState';
import { openSourcesInMentra } from './sourcePreference';

// Frame only public HTTPS hosts, with no credentials, custom ports or app routes.
function previewUrl(href: string) {
  try {
    const url = new URL(href);
    if (url.protocol === 'https:' && url.origin !== location.origin && !url.port && !url.username && !url.password
        && /^[a-z\d.-]+\.[a-z]{2,}$/i.test(url.hostname)
        && !/\.(?:local|internal|localhost|test|invalid|onion)$/i.test(url.hostname)) return url;
  } catch { /* Relative links stay in their normal navigation path. */ }
  return undefined;
}

function WebSourcePreview({ url, title, excerpt }: { url: URL; title: string; excerpt?: string }) {
  return <div className="workspace-web-preview">
    <header className="space-y-2 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="min-w-0 break-all text-xs text-muted">{url.hostname}</span>
        <a href={url.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer"
          className={buttonStyles({ size: 'sm', variant: 'secondary' })}>Open in browser <ExternalLink size={14} aria-hidden="true" /></a>
      </div>
      {excerpt && <p className="text-sm leading-6 text-body">{excerpt}</p>}
      <p className="text-xs text-muted">If the publisher blocks this preview, use Open in browser.</p>
    </header>
    <iframe src={url.href} title={title} sandbox="allow-scripts" referrerPolicy="no-referrer" {...{ credentialless: '' }} />
  </div>;
}

interface SourceLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href' | 'onClick'> {
  href: string;
  sourceTitle?: string;
  excerpt?: string;
  onPreview?: () => void;
}

/** A real link preserves the browser's modifier, middle-click and context-menu actions. */
export function SourceLink({ href, sourceTitle, excerpt, onPreview, children, ...props }: SourceLinkProps) {
  const panel = useSidePanelActions();
  const external = /^https?:\/\//i.test(href);
  return <a {...props} href={href} target={external ? '_blank' : props.target} rel="noopener noreferrer" referrerPolicy="no-referrer"
    onClick={event => {
      if (!panel || !openSourcesInMentra() || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const url = previewUrl(href);
      if (!url) return;
      event.preventDefault();
      onPreview?.();
      const title = sourceTitle?.trim() || event.currentTarget.textContent?.trim() || url.hostname;
      panel.open({ title, icon: <Globe size={14} aria-hidden="true" />, content: <WebSourcePreview url={url} title={title} excerpt={excerpt} /> });
    }}>{children}</a>;
}

export function SourceMarkdownLink({ href, children }: Pick<SourceLinkProps, 'children'> & { href?: string }) {
  return href ? <SourceLink href={href}>{children}</SourceLink> : <span>{children}</span>;
}
