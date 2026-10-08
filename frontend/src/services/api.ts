import type { ChatResponse, ChatTurn } from '../types/chat';
import type { ChatSelection } from '../types/rag';

const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

async function withResponse<T>(url: string, init: RequestInit, consume: (response: Response) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  const parent = init.signal;
  const cancel = () => controller.abort(parent?.reason);
  if (parent?.aborted) cancel();
  else parent?.addEventListener('abort', cancel, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 120_000);
  try {
    return await consume(await fetch(url, { credentials: 'include', ...init, signal: controller.signal }));
  } catch (error) {
    if (parent?.aborted) throw error;
    if (timedOut) throw new ApiError('The request took too long. Try again.', 0, 'REQUEST_TIMEOUT');
    if (error instanceof TypeError) throw new ApiError('Couldn’t reach Mentra. Check your connection and try again.', 0, 'NETWORK_ERROR');
    throw error;
  } finally {
    clearTimeout(timer);
    parent?.removeEventListener('abort', cancel);
  }
}

export interface HealthResponse {
  status: string;
  service: string;
}

interface ApiErrorResponse {
  error?: {
    code?: string;
    message?: string;
    details?: ValidationIssue[];
  };
}

export interface ValidationIssue {
  location: (string | number)[];
  message: string;
  type: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly details: ValidationIssue[] = [],
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }
  if (
    typeof init.body === 'string' &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json');
  }

  const url = `${apiBaseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
  return withResponse(url, { ...init, headers }, async response => {
  const bodyText = await response.text();
  let body: unknown;

  if (bodyText) {
    try {
      body = JSON.parse(bodyText) as unknown;
    } catch {
      throw new ApiError(
        'Backend returned an invalid JSON response.',
        response.status,
        'INVALID_RESPONSE',
      );
    }
  }

  if (!response.ok) {
    const apiError = body as ApiErrorResponse | undefined;
    throw new ApiError(
      apiError?.error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      apiError?.error?.code ?? 'HTTP_ERROR',
      apiError?.error?.details ?? [],
    );
  }

    return body as T;
  });
}

export async function fetchHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>('/api/v1/health');
}

export async function sendChatMessage(
  messages: ChatTurn[],
  signal?: AbortSignal,
  retrieval?: ChatSelection,
): Promise<ChatResponse> {
  return apiRequest<ChatResponse>('/api/v1/chat', {
    method: 'POST',
    body: JSON.stringify({ messages, retrieval }),
    signal,
  });
}

export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  return withResponse(`${apiBaseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`, { signal }, async response => {
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ApiErrorResponse;
    throw new ApiError(body.error?.message ?? 'This source is unavailable.', response.status, body.error?.code ?? 'HTTP_ERROR');
  }
    return response.blob();
  });
}
