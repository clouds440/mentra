import { hasPendingPages } from './pageCache';
import { progressPage } from './learning';
import { libraryPage } from './rag';
import { assessments } from './assessments';

let busy = false;
// Intent only: no timer, no full-workspace warmup, and no competing read burst.
export function prefetchPage(path: string, assessmentId?: string) {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  if (busy || hasPendingPages() || document.hidden || connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType ?? '')) return;
  const signal = new AbortController().signal;
  const read = path === '/progress' ? () => progressPage(signal)
    : path === '/library' ? () => libraryPage(0, false, signal)
    : path === '/assessments' ? () => assessments.page(signal, 'assessments', assessmentId) : undefined;
  if (!read) return;
  busy = true;
  void read().catch(() => {}).finally(() => { busy = false; });
}
