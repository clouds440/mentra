import type { ReactNode } from 'react';
import type { WebSource } from '../../types/webSearch';
import { safeWebsite, WebsiteIcon } from './WebsiteIcon';

export function safeSource(source: WebSource): boolean {
  try {
    const url = new URL(source.url);
    return safeWebsite(source) && ['https:', 'http:'].includes(url.protocol) && url.hostname === source.domain
      && !url.username && !url.password && !url.port;
  } catch { return false; }
}

export function WebCitation({ source, children }: { source: WebSource; children?: ReactNode }) {
  if (!safeSource(source)) return <span>{children ?? `[${source.token}]`}</span>;
  return <a href={source.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer"
    title={`${source.title} · ${source.domain}`} aria-label={`Open web source ${source.token}: ${source.title} on ${source.domain} (new tab)`}
    className="inline-flex max-w-full items-center gap-1 rounded-md px-1 text-accent underline decoration-accent/40 underline-offset-2 hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
    <WebsiteIcon website={source} /><span>{children ?? `[${source.token}]`}</span>
  </a>;
}
