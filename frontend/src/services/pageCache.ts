// Small, in-memory page cache. Live chat, grading and job polling stay outside it.
const entries = new Map<string, { value: unknown; saved: number }>();
const pending = new Map<string, { controller: AbortController; promise: Promise<unknown>; consumers: number }>();
const controllers = new Set<AbortController>();
let owner: string | null = null;
let changes: BroadcastChannel | undefined;
export type PageScope = 'documents' | 'learning-contexts' | 'rag' | 'learning' | 'events' | 'event-proposals' | 'memories' | 'notifications' | 'assessments';
const listeners = new Set<(scopes?: readonly PageScope[]) => void>();
export function subscribePageChanges(listener: (scopes?: readonly PageScope[]) => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
function matches(key: string, scopes?: readonly PageScope[]) {
  return !scopes || scopes.some(scope => key.startsWith(`/api/v1/${scope}/`) || key.startsWith(`/api/v1/${scope}?`) || key.startsWith(`/api/v1/${scope}[`));
}
export function invalidatePageCache(scopes?: readonly PageScope[], notify = false, broadcast = true) {
  for (const key of entries.keys()) if (matches(key, scopes)) entries.delete(key);
  for (const [key, request] of pending) if (matches(key, scopes)) { pending.delete(key); request.controller.abort(); }
  if (notify) {
    listeners.forEach(listener => listener(scopes));
    if (broadcast) changes?.postMessage(scopes ?? null);
  }
}
// Mutations invalidate only dependent domains; read-only POSTs do not evict pages.
export function invalidateMutation(path: string) {
  if (/\/(preview|search|export|transcribe)(\?|$)/.test(path)) return;
  const domain = path.split('?')[0].split('/')[3];
  const dependencies: Record<string, PageScope[]> = {
    assessments: ['assessments', 'learning'], learning: ['learning', 'assessments'],
    documents: ['documents', 'learning', 'assessments'], 'learning-contexts': ['learning-contexts', 'documents', 'learning', 'assessments'],
    events: ['events', 'event-proposals', 'notifications'], 'event-proposals': ['events', 'event-proposals', 'notifications'],
    memories: ['memories'], notifications: ['notifications'],
    'student-profile': ['learning', 'learning-contexts'],
  };
  if (dependencies[domain]) invalidatePageCache(dependencies[domain], true);
}
export function setPageCacheOwner(next: string | null) {
  if (owner === next) return;
  for (const controller of controllers) controller.abort();
  controllers.clear();
  invalidatePageCache();
  owner = next;
  changes?.close(); changes = undefined;
  if (next && typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined') {
    changes = new BroadcastChannel(`mentra-pages-${next}`);
    changes.onmessage = ({ data }) => {
      if (data === null || Array.isArray(data) && data.every(scope => typeof scope === 'string')) {
        invalidatePageCache(data ?? undefined, true, false);
      }
    };
  }
}
export function cacheablePage(path: string, init: RequestInit) {
  return owner !== null && (!init.method || init.method === 'GET') && !init.cache &&
    /^\/api\/v1\/(documents|learning-contexts|rag\/capabilities|learning|events|event-proposals|memories|notifications|assessments)(\/|\?|$)/.test(path) &&
    !/\/assessments\/attempts\/|\/chat-drafts|\/jobs|\/sync|\/unread/.test(path);
}
export function hasPendingPages() { return pending.size > 0; }
function inProgress(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  if (Array.isArray(value)) return value.some(inProgress);
  const record = value as Record<string, unknown>;
  if (typeof record.state === 'string' && ['QUEUED', 'RUNNING', 'RETRY_WAIT', 'submitted', 'grading', 'pending_transcription'].includes(record.state)) return true;
  return Object.values(record).some(inProgress);
}
export async function cachedPage<T>(key: string, load: (signal: AbortSignal) => Promise<T>, signal?: AbortSignal | null): Promise<T> {
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  const saved = entries.get(key);
  if (saved && Date.now() - saved.saved < (key.startsWith('/api/v1/assessments/mistakes?') ? 300_000 : 30_000)) return saved.value as T;
  if (saved) entries.delete(key);
  let request = pending.get(key);
  if (!request) {
    const controller = new AbortController();
    controllers.add(controller);
    const promise = Promise.resolve().then(() => load(controller.signal)).then(value => {
      if (controller.signal.aborted || pending.get(key)?.promise !== promise) throw new DOMException('Aborted', 'AbortError');
      if (pending.get(key)?.promise === promise && !controller.signal.aborted && !inProgress(value)) {
        if (entries.size >= 128) entries.delete(entries.keys().next().value!);
        entries.set(key, { value, saved: Date.now() });
      }
      return value;
    }).finally(() => { controllers.delete(controller); if (pending.get(key)?.promise === promise) pending.delete(key); });
    request = { controller, promise, consumers: 0 }; pending.set(key, request);
  }
  request.consumers++;
  return new Promise<T>((resolve, reject) => {
    let released = false;
    const release = () => {
      if (released) return;
      released = true; request!.consumers--;
      if (!request!.consumers) setTimeout(() => {
        if (!request!.consumers && pending.get(key) === request) { pending.delete(key); request!.controller.abort(); }
      }, 0);
    };
    const cancel = () => { release(); reject(new DOMException('Aborted', 'AbortError')); };
    signal?.addEventListener('abort', cancel, { once: true });
    request!.promise.then(value => { if (!signal?.aborted) resolve(value as T); }, reject)
      .finally(() => { signal?.removeEventListener('abort', cancel); release(); });
  });
}
