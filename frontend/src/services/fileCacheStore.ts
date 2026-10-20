/** Session memory only: no file bytes enter browser storage or the HTTP cache. */
export class FileCacheStore {
  private values = new Map<string, Blob>();
  private pending = new Map<string, { controller: AbortController; promise: Promise<Blob> }>();

  constructor(private load: (path: string, signal: AbortSignal) => Promise<Blob>) {}

  get(owner: string, path: string): Promise<Blob> {
    const key = JSON.stringify([owner, path]);
    const saved = this.values.get(key);
    if (saved) return Promise.resolve(saved);
    const active = this.pending.get(key);
    if (active) return active.promise;
    const controller = new AbortController();
    const promise = this.load(path, controller.signal).then(blob => {
      if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
      this.values.set(key, blob);
      return blob;
    }).finally(() => { if (this.pending.get(key)?.promise === promise) this.pending.delete(key); });
    this.pending.set(key, { controller, promise });
    return promise;
  }

  clear(owner: string, prefix = '') {
    const matches = (key: string) => {
      const [savedOwner, path] = JSON.parse(key) as [string, string];
      return savedOwner === owner && path.startsWith(prefix);
    };
    for (const key of this.values.keys()) if (matches(key)) this.values.delete(key);
    for (const [key, request] of this.pending) if (matches(key)) {
      this.pending.delete(key); request.controller.abort();
    }
  }
}
