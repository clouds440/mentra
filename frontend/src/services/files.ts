import { apiRequest, ApiError } from './api';
import { sessionFile } from './fileSessionCache';

export type FilePurpose = 'chat' | 'library' | 'assessment' | 'speech';
export interface StoredFile { id: string; filename: string; size_bytes: number; media_type: string; state: string; purpose: string }
let operations = new WeakMap<Blob, Map<string, { key: string; until: number }>>();
let receipts = new WeakMap<Blob, Map<string, { value: StoredFile; until: number }>>();
let uploadOwner: string | null = null;
let uploadEpoch = 0;

export function setUploadOwner(owner: string | null) {
  if (owner === uploadOwner) return;
  uploadOwner = owner; uploadEpoch++;
  operations = new WeakMap(); receipts = new WeakMap();
}

/** Keep the receipt key across retries of the same locally staged file. */
export async function uploadFile(file: Blob, filename: string, purpose: FilePurpose, signal?: AbortSignal): Promise<StoredFile> {
  const epoch = uploadEpoch;
  const current = () => {
    if (epoch !== uploadEpoch || signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  };
  current();
  const cacheKey = JSON.stringify([purpose, filename]);
  const existing = receipts.get(file)?.get(cacheKey);
  const now = performance.now();
  if (existing && now < existing.until) return existing.value;
  // Keep retry state shorter than server staging expiry (speech 15m, others 24h).
  // A day-old failed send must upload under a fresh key instead of replaying a
  // permanently expired original. Use a monotonic clock for clock corrections.
  const lifetime = purpose === 'speech' ? 10 * 60_000 : 23 * 60 * 60_000;
  let purposes = operations.get(file);
  if (!purposes) { purposes = new Map(); operations.set(file, purposes); }
  let operation = purposes.get(cacheKey);
  if (!operation || now >= operation.until) {
    operation = { key: crypto.randomUUID(), until: now + lifetime };
    purposes.set(cacheKey, operation);
  }
  const key = operation.key;
  const body = new FormData();
  body.append('file', file, filename); body.append('purpose', purpose); body.append('operation_key', key);
  let stored: StoredFile;
  try {
    stored = await apiRequest<StoredFile>('/api/v1/files/uploads', { method: 'POST', body, signal });
  } catch (failure) {
    current();
    if (signal?.aborted || !(failure instanceof ApiError) || (failure.status !== 0 && failure.status !== 503 && failure.code !== 'FILES_PENDING')) throw failure;
    // Recover a successful upload whose response was lost without sending the bytes again.
    const recovered = await apiRequest<StoredFile>(`/api/v1/files/uploads/${encodeURIComponent(key)}`, { signal });
    if (!['STAGED', 'ACTIVE'].includes(recovered.state)) throw failure;
    stored = recovered;
  }
  current();
  let saved = receipts.get(file);
  if (!saved) { saved = new Map(); receipts.set(file, saved); }
  saved.set(cacheKey, { value: stored, until: operation.until });
  return stored;
}

/** Domain routes resolve their binding and delegate to the Files delivery layer. */
export const downloadFile = (path: string, signal?: AbortSignal) => sessionFile(path, signal);
export const cancelUpload = (id: string, signal?: AbortSignal) => apiRequest<void>(`/api/v1/files/uploads/${id}`, { method: 'DELETE', signal });
