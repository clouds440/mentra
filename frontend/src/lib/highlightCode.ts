let worker: Worker | undefined;
let sequence = 0;
const pending = new Map<number, { finish: (html: string | null) => void; timer: ReturnType<typeof setTimeout> }>();
function reset() {
  worker?.terminate(); worker = undefined;
  for (const job of pending.values()) { clearTimeout(job.timer); job.finish(null); }
  pending.clear();
}
export function highlightCode(code: string, language: string): { result: Promise<string | null>; cancel: () => void } {
  if (language === 'plain' || code.length > 80_000 || typeof Worker === 'undefined') return { result: Promise.resolve(null), cancel: () => {} };
  let id = 0;
  const result = new Promise<string | null>(finish => {
    try {
      if (!worker) {
        worker = new Worker(new URL('./prism.worker.ts', import.meta.url), { type: 'module' });
        worker.onmessage = ({ data }: MessageEvent<{ id: number; html: string | null }>) => {
          const job = pending.get(data.id);
          if (job) { clearTimeout(job.timer); pending.delete(data.id); job.finish(data.html); }
        };
        worker.onerror = reset;
      }
      id = ++sequence;
      pending.set(id, { finish, timer: setTimeout(reset, 12_000) });
      worker.postMessage({ id, code, language });
    } catch { reset(); finish(null); }
  });
  return { result, cancel: () => { const job = pending.get(id); if (job) { clearTimeout(job.timer); pending.delete(id); job.finish(null); } } };
}
