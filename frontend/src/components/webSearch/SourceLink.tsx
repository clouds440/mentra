import { Globe } from 'lucide-react';
import { useContext, type AnchorHTMLAttributes } from 'react';
import { PanelResourceScope, PanelTabScope, useSidePanelActions } from '../workspace/sidePanelState';
import { openSourcesInMentra } from './sourcePreference';

// Frame only public HTTPS hosts, with no credentials, custom ports or app routes.
export function previewUrl(href: string) {
  try {
    const url = new URL(href);
    const host = url.hostname.replace(/\.$/, '');
    if (url.protocol === 'https:' && url.origin !== location.origin && !url.port && !url.username && !url.password
        && /^(?:[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?\.)+[a-z]{2,}$/i.test(host)
        && !/(?:^|\.)(?:localhost|local|internal|test|invalid|example|onion|lan|corp|home\.arpa)$/i.test(host)) return url;
  } catch { /* Relative links stay in their normal navigation path. */ }
  return undefined;
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
        icon: <Globe size={14} aria-hidden="true" /> });
    }}>{children}</a>;
}

export function SourceMarkdownLink({ href, children }: Pick<SourceLinkProps, 'children'> & { href?: string }) {
  return href ? <SourceLink href={href}>{children}</SourceLink> : <span>{children}</span>;
}
