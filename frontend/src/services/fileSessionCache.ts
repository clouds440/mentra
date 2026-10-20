import { apiBlob, ApiError, subscribeApiMutations } from './api';
import { FileCacheStore } from './fileCacheStore';

const local = new FileCacheStore(apiBlob);
let owner: string | null = null;
let epoch = 0, sequence = 0;
let worker: SharedWorker | undefined;
let workerUnavailable = false;
class WorkerUnavailable extends Error {}
type CacheResult = { blob?: Blob; version: number };
const pending = new Map<number, { resolve: (result: CacheResult) => void; reject: (error: Error) => void }>();

function sharedWorker() {
  if (worker || workerUnavailable) return worker;
  try {
    worker = new SharedWorker(new URL('./fileSessionCache.worker.ts', import.meta.url), { type: 'module', name: 'mentra-session-files-v1' });
    worker.onerror = event => {
      event.preventDefault();
      workerUnavailable = true; worker?.port.close(); worker = undefined;
      for (const request of pending.values()) request.reject(new WorkerUnavailable());
      pending.clear();
    };
    worker.port.onmessage = ({ data }: MessageEvent<CacheResult & { id: number }>) => {
      const request = pending.get(data.id);
      if (!request) return;
      pending.delete(data.id);
      request.resolve(data);
    };
    worker.port.start();
    worker.port.postMessage({ type: 'owner', owner });
  } catch { workerUnavailable = true; worker = undefined; }
  return worker;
}

export function setFileCacheOwner(next: string | null) {
  if (next === owner) return;
  if (owner) {
    local.clear(owner);
    // Logout must also clear another tab's cache when this tab has not opened
    // a file yet. Connect to the shared session before clearing that owner.
    sharedWorker()?.port.postMessage({ type: 'clear', owner });
  }
  owner = next; epoch++;
  for (const request of pending.values()) request.reject(new DOMException('Aborted', 'AbortError'));
  pending.clear();
  worker?.port.postMessage({ type: 'owner', owner });
}

function invalidate(prefix: string) {
  if (!owner) return;
  local.clear(owner, prefix);
  sharedWorker()?.port.postMessage({ type: 'clear', owner, prefix });
}
subscribeApiMutations((path, method) => {
  const route = path.split('?')[0];
  if (/^\/api\/v1\/events\/[^/]+$/.test(route)) invalidate(route + '/calendar');
  if (method !== 'DELETE' && method !== 'PATCH') return;
  if (/^\/api\/v1\/(documents|chat-attachments|files)\/[^/]+$/.test(route)) invalidate(route + '/');
  const conversation = /^\/api\/v1\/conversations\/([^/]+)$/.exec(route);
  // Chat source URLs carry the conversation as a query parameter.
  if (conversation) { invalidate('/api/v1/chat-attachments/'); }
});

export async function sessionFile(path: string, signal?: AbortSignal): Promise<Blob> {
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  if (!owner) return apiBlob(path, signal);
  const requestedOwner = owner, requestedEpoch = epoch;
  const shared = sharedWorker();
  let detach = () => {};
  const operation = shared ? new Promise<CacheResult>((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new ApiError('File timed out.', 0, 'REQUEST_TIMEOUT')); }, 125_000);
    detach = () => { clearTimeout(timer); pending.delete(id); };
    pending.set(id, { resolve, reject });
    shared.port.postMessage({ type: 'get', id, path });
  }).then(async result => {
    if (result.blob) return result.blob;
    if (owner !== requestedOwner || epoch !== requestedEpoch) throw new DOMException('Aborted', 'AbortError');
    const blob = await local.get(requestedOwner, path);
    if (owner !== requestedOwner || epoch !== requestedEpoch) throw new DOMException('Aborted', 'AbortError');
    shared.port.postMessage({ type: 'put', path, blob, version: result.version });
    local.clear(requestedOwner, path);
    return blob;
  }).catch(error => {
    if (error instanceof WorkerUnavailable && owner === requestedOwner && epoch === requestedEpoch) return local.get(requestedOwner, path);
    throw error;
  }) : local.get(requestedOwner, path);
  return new Promise<Blob>((resolve, reject) => {
    const cancel = () => { detach(); reject(new DOMException('Aborted', 'AbortError')); };
    signal?.addEventListener('abort', cancel, { once: true });
    operation.then(blob => {
      if (epoch !== requestedEpoch || owner !== requestedOwner || signal?.aborted) cancel();
      else resolve(blob);
    }, reject).finally(() => { detach(); signal?.removeEventListener('abort', cancel); });
  });
}
