import { apiRequest, ApiError } from './api';
import type { AuthCredentials, AuthIdentity } from '../types/auth';

async function authRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  init.signal?.addEventListener('abort', cancel, { once: true });
  if (init.signal?.aborted) cancel();
  const timeout = window.setTimeout(cancel, 15_000);
  try {
    const headers = new Headers(init.headers);
    headers.set('X-Mentra-Session', 'cookie');
    return await apiRequest<T>(`/api/v1/auth/${path}`, {
      ...init,
      headers,
      signal: controller.signal,
      cache: 'no-store',
    });
  } finally {
    window.clearTimeout(timeout);
    init.signal?.removeEventListener('abort', cancel);
  }
}

export function getSession(signal?: AbortSignal): Promise<AuthIdentity> {
  return authRequest<AuthIdentity>('me', { signal });
}

export function login(credentials: AuthCredentials): Promise<AuthIdentity> {
  return authRequest<AuthIdentity>('login', { method: 'POST', body: JSON.stringify(credentials) });
}

export function register(credentials: AuthCredentials): Promise<AuthIdentity> {
  return authRequest<AuthIdentity>('register', { method: 'POST', body: JSON.stringify(credentials) });
}

export function logout(): Promise<void> {
  return authRequest<void>('logout', { method: 'POST' });
}

export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'AUTHENTICATION_FAILED') return 'That username or password isn’t correct.';
    if (error.status === 422) return 'Check your username and password and try again.';
    if (error.status >= 500) return 'Mentra is temporarily unavailable. Please try again shortly.';
    return error.message;
  }
  return 'Couldn’t reach Mentra. Check your connection and try again.';
}
