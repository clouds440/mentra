const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export interface HealthResponse {
  status: string;
  service: string;
}

interface ApiErrorResponse {
  error?: {
    code?: string;
    message?: string;
  };
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
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
  const response = await fetch(url, { ...init, headers });
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
    );
  }

  return body as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>('/api/v1/health');
}
