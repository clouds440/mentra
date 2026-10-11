import { useState } from 'react';
import { Globe } from 'lucide-react';
import type { WebsiteIdentity } from '../../types/webSearch';

export function safeWebsite(value: WebsiteIdentity): boolean {
  try {
    const url = new URL(value.favicon_url);
    return url.protocol === 'https:' && url.hostname === value.domain && value.domain.includes('.')
      && !url.username && !url.password && !url.port && url.pathname === '/favicon.ico' && !url.search && !url.hash
      && !/^\d[\d.]*$/.test(value.domain) && !/\.(local|internal|test|invalid|localhost|onion)$/.test(value.domain);
  } catch { return false; }
}

/** Icons are optional, anonymous origin requests; unavailable/CORS-blocked icons have a stable fallback. */
export function WebsiteIcon({ website }: { website: WebsiteIdentity }) {
  const [failedUrl, setFailedUrl] = useState<string>();
  return <span aria-hidden="true" className="inline-flex h-4 w-4 shrink-0 items-center justify-center align-middle">
    {safeWebsite(website) && failedUrl !== website.favicon_url
      ? <img src={website.favicon_url} alt="" className="h-4 w-4 rounded-sm object-contain" loading="lazy" decoding="async"
          crossOrigin="anonymous" referrerPolicy="no-referrer" onError={() => setFailedUrl(website.favicon_url)} />
      : <Globe className="h-3.5 w-3.5 text-subtle" />}
  </span>;
}
