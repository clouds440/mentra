// Small, in-memory page cache. Live chat, grading and job polling stay outside it.
const entries = new Map<string, { expires: number; value: unknown }>();
const pending = new Map<string, { controller: AbortController; promise: Promise<unknown> }>();
const controllers = new Set<AbortController>();
let owner: string | null = null;
let generation = 0;
export function invalidatePageCache() {
  generation++;
  entries.clear();
  pending.clear();
}
export function setPageCacheOwner(next: string | null) {
  if (owner === next) return;
  for (const controller of controllers) controller.abort();
  controllers.clear();
  invalidatePageCache();
  owner = next;
}
export function cacheablePage(path: string, init: RequestInit) {
  return owner !== null && (!init.method || init.method === 'GET') && !init.cache &&
    /^\/api\/v1\/(documents|learning-contexts|rag\/capabilities|learning|events|event-proposals|memories|notifications|assessments)(\/|\?|$)/.test(path) &&
    !/\/assessments\/attempts\/|\/chat-drafts|\/jobs|\/sync|\/unread/.test(path);
}
function inProgress(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  if (Array.isArray(value)) return value.some(inProgress);
  const record = value as Record<string, unknown>;
  if (typeof record.state === 'string' && ['QUEUED', 'RUNNING', 'RETRY_WAIT', 'submitted', 'grading', 'draft', 'pending_transcription'].includes(record.state)) return true;
  return Object.values(record).some(inProgress);
}
export async function cachedPage<T>(key: string, load: (signal: AbortSignal) => Promise<T>, signal?: AbortSignal | null): Promise<T> {
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  const saved = entries.get(key);
  if (saved && saved.expires > Date.now()) return saved.value as T;
  let request = pending.get(key);
  if (!request) {
    const epoch = generation, controller = new AbortController();
    controllers.add(controller);
    const promise = Promise.resolve().then(() => load(controller.signal)).then(value => {
      if (epoch === generation && !inProgress(value)) {
        if (entries.size >= 128) entries.delete(entries.keys().next().value!);
        entries.set(key, { value, expires: Date.now() + 30_000 });
      }
      return value;
    }).finally(() => { controllers.delete(controller); if (pending.get(key)?.promise === promise) pending.delete(key); });
    request = { controller, promise }; pending.set(key, request);
  }
  return new Promise<T>((resolve, reject) => {
    const cancel = () => reject(new DOMException('Aborted', 'AbortError'));
    signal?.addEventListener('abort', cancel, { once: true });
    request!.promise.then(value => { if (!signal?.aborted) resolve(value as T); }, reject)
      .finally(() => signal?.removeEventListener('abort', cancel));
  });
}
