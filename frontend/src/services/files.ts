import { apiRequest, apiBlob, ApiError } from './api';

export type FilePurpose = 'chat' | 'library' | 'assessment' | 'speech';
export interface StoredFile { id: string; filename: string; size_bytes: number; media_type: string; state: string; purpose: string }
const operations = new WeakMap<Blob, Map<string, string>>();
const receipts = new WeakMap<Blob, Map<string, StoredFile>>();

/** Keep the receipt key across retries of the same locally staged file. */
export async function uploadFile(file: Blob, filename: string, purpose: FilePurpose, signal?: AbortSignal): Promise<StoredFile> {
  const existing = receipts.get(file)?.get(purpose);
  if (existing) return existing;
  let purposes = operations.get(file);
  if (!purposes) { purposes = new Map(); operations.set(file, purposes); }
  let key = purposes.get(purpose);
  if (!key) { key = crypto.randomUUID(); purposes.set(purpose, key); }
  const body = new FormData();
  body.append('file', file, filename); body.append('purpose', purpose); body.append('operation_key', key);
  let stored: StoredFile;
  try {
    stored = await apiRequest<StoredFile>('/api/v1/files/uploads', { method: 'POST', body, signal });
  } catch (failure) {
    if (signal?.aborted || !(failure instanceof ApiError) || (failure.status !== 0 && failure.status !== 503 && failure.code !== 'FILES_PENDING')) throw failure;
    // Recover a successful upload whose response was lost without sending the bytes again.
    const recovered = await apiRequest<StoredFile>(`/api/v1/files/uploads/${encodeURIComponent(key)}`, { signal });
    if (!['STAGED', 'ACTIVE'].includes(recovered.state)) throw failure;
    stored = recovered;
  }
  let saved = receipts.get(file);
  if (!saved) { saved = new Map(); receipts.set(file, saved); }
  saved.set(purpose, stored);
  return stored;
}

/** Domain routes resolve their binding and delegate to the Files delivery layer. */
export const downloadFile = (path: string, signal?: AbortSignal) => apiBlob(path, signal);
export const cancelUpload = (id: string, signal?: AbortSignal) => apiRequest<void>(`/api/v1/files/uploads/${id}`, { method: 'DELETE', signal });
