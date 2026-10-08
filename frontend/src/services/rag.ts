import { apiRequest, apiBlob } from './api';
import type { MaterialList, MaterialDocument, MaterialVersion, MaterialJob, LearningContext, UploadResult, RAGCapabilities, SourceChunk } from '../types/rag';

const path = (id: string) => `/api/v1/documents/${encodeURIComponent(id)}`;
export const listMaterials = (offset = 0, archived?: boolean, signal?: AbortSignal, contextId?: string) => apiRequest<MaterialList>(`/api/v1/documents?offset=${offset}${archived === undefined ? '' : `&archived=${archived}`}${contextId ? `&context_id=${encodeURIComponent(contextId)}` : ''}`, { signal });
export const getMaterial = (id: string, signal?: AbortSignal) => apiRequest<MaterialDocument>(path(id), { signal });
export const listVersions = (id: string, offset: number, signal?: AbortSignal) => apiRequest<{ items: MaterialVersion[]; total: number }>(`${path(id)}/versions?offset=${offset}`, { signal });
export const getCapabilities = (signal?: AbortSignal) => apiRequest<RAGCapabilities>('/api/v1/rag/capabilities', { signal });
export async function listContexts(signal?: AbortSignal): Promise<LearningContext[]> {
  const contexts: LearningContext[] = [];
  let page: LearningContext[];
  do {
    page = await apiRequest<LearningContext[]>(`/api/v1/learning-contexts?offset=${contexts.length}&limit=100`, { signal });
    contexts.push(...page);
  } while (page.length === 100);
  return contexts;
}
export const createContext = (name: string, activate: boolean) => apiRequest<LearningContext>('/api/v1/learning-contexts', { method: 'POST', body: JSON.stringify({ name, activate }) });
export const transitionContext = (id: string, status: string) => apiRequest<LearningContext>(`/api/v1/learning-contexts/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ status }) });
export function uploadMaterial(file: File, title: string, contextIds: string[], key: string, signal?: AbortSignal, replacement?: MaterialDocument) {
  const body = new FormData();
  body.append('file', file); body.append('title', title); body.append('context_ids', JSON.stringify(contextIds)); body.append('idempotency_key', key);
  if (replacement) body.append('expected_revision', String(replacement.revision));
  return apiRequest<UploadResult>(replacement ? `${path(replacement.id)}/versions` : '/api/v1/documents', { method: 'POST', body, signal });
}
export const updateMaterial = (doc: MaterialDocument, values: { title?: string; archived?: boolean; context_ids?: string[] }) => apiRequest<MaterialDocument>(path(doc.id), { method: 'PATCH', body: JSON.stringify({ expected_revision: doc.revision, ...values }) });
export const deleteMaterial = (id: string) => apiRequest<{ state: string }>(path(id), { method: 'DELETE' });
export const reindexMaterial = (doc: MaterialDocument) => apiRequest<MaterialJob>(`${path(doc.id)}/reindex`, { method: 'POST', body: JSON.stringify({ expected_revision: doc.revision, idempotency_key: crypto.randomUUID() }) });
export const retryJob = (id: string) => apiRequest<MaterialJob>(`/api/v1/rag/jobs/${encodeURIComponent(id)}/retry`, { method: 'POST' });
export const tagMaterial = (doc: MaterialDocument, labels: string[]) => apiRequest<{ document: MaterialDocument; unresolved_labels: string[] }>(`${path(doc.id)}/concepts`, { method: 'POST', body: JSON.stringify({ expected_revision: doc.revision, labels }) });
const versionPath = (id: string, version: string) => `${path(id)}/versions/${encodeURIComponent(version)}`;
export const downloadSource = (id: string, version: string, archived: boolean, signal?: AbortSignal) => apiBlob(`${versionPath(id, version)}/source?include_archived=${archived}`, signal);
export const getSourceChunks = (id: string, version: string, archived: boolean, signal?: AbortSignal, offset = 0, generation?: string) => apiRequest<SourceChunk[]>(`${versionPath(id, version)}/chunks?include_archived=${archived}&offset=${offset}${generation ? `&generation_id=${encodeURIComponent(generation)}` : ''}`, { signal });
export const pendingJob = (doc: MaterialDocument) => doc.jobs.find(j => ['QUEUED', 'RUNNING', 'RETRY_WAIT'].includes(j.state));
export const materialError = (error: unknown) => error instanceof Error ? error.message : 'Could not reach your material. Try again.';
