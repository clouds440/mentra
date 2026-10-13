import type { WebSource, WebSearchRecord } from '../../types/webSearch';
import { WebCitation } from './WebCitation';
import { webSearchWarningMessage } from '../../services/userError';

function civilDate(value: string | null | undefined): string | undefined {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.valueOf()) ? undefined : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(date);
}
function instant(value: string, zone: string): string {
  try { return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: zone }).format(new Date(value)); }
  catch { return value.slice(0, 10); }
}

export function WebCitations({ sources = [], citations = [], searches = [] }: {
  sources?: WebSource[]; citations?: string[]; searches?: WebSearchRecord[];
}) {
  if (!sources.length) return null;
  const zone = searches[searches.length - 1]?.reference_timezone ?? 'UTC';
  const limitations = searches.filter(search => !['ok', 'no_results'].includes(search.outcome));
  return <div className="mt-4 text-sm">
    {searches.some(search => search.cache_hit) && <p className="mb-2 text-xs text-subtle">Recently cached web results were reused; original search dates are shown below.</p>}
    {!!sources.length && <details className="rounded-xl border border-border px-3 py-2">
      <summary className="cursor-pointer text-muted">Web sources ({sources.length})</summary>
      <ol className="mt-3 space-y-3">{sources.slice(0, 10).map(source => <li key={source.token} className="min-w-0">
        <WebCitation source={source}><span className="break-words">[{source.token}] {source.title}</span></WebCitation>
        <p className="mt-1 text-xs text-subtle">{citations.includes(source.token) ? 'Cited' : 'Consulted'} · {source.domain}</p>
        <p className="text-xs text-subtle">{source.source_date_status === 'future' ? 'Source date is in the future; verify it.'
          : source.source_date_status === 'available' && civilDate(source.published_date) ? `Published ${civilDate(source.published_date)}` : 'Publication date unavailable'}
          {source.updated_date && ` · Updated ${civilDate(source.updated_date) ?? 'date unavailable'}`}
          {source.data_as_of && ` · Data as of ${source.data_as_of}`}</p>
        <p className="text-xs text-subtle">Searched {instant(source.searched_at, zone)} ({zone})</p>
        {source.excerpt && <p className="mt-1 line-clamp-2 break-words text-xs leading-5 text-muted">{source.excerpt}</p>}
      </li>)}</ol>
    </details>}
  </div>;
}
