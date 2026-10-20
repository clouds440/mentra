export {};

// SharedWorker lifetime is owned by open documents. No persistent cache, timers
// or background service worker keep private originals after all tabs close.
const values = new Map<string, Blob>();
const versions = new Map<string, number>();
const scope = self as unknown as { onconnect: (event: MessageEvent) => void };
scope.onconnect = event => {
  const port = event.ports[0];
  let owner: string | null = null;
  port.onmessage = ({ data }: MessageEvent<{ type: string; owner?: string | null; prefix?: string; id: number; path: string; blob: Blob; version: number }>) => {
    if (data.type === 'owner') { owner = data.owner ?? null; return; }
    if (data.type === 'clear' && data.owner) {
      const clearedOwner = data.owner;
      versions.set(clearedOwner, (versions.get(clearedOwner) ?? 0) + 1);
      for (const key of values.keys()) {
        const [savedOwner, path] = JSON.parse(key) as [string, string];
        if (savedOwner === clearedOwner && path.startsWith(data.prefix ?? '')) values.delete(key);
      }
      return;
    }
    if (!owner) return;
    const key = JSON.stringify([owner, data.path]);
    const version = versions.get(owner) ?? 0;
    if (data.type === 'get') port.postMessage({ id: data.id, blob: values.get(key), version });
    if (data.type === 'put' && data.version === version) values.set(key, data.blob);
  };
  port.start();
};
