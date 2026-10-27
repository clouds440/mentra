import { useEffect, useMemo, useRef, useState } from 'react';
import { observeVisible } from './DeferredVisual';
import { diagramCacheGeneration, onRichContentOwnerChange } from '../../lib/richContentCache';

const LIMIT = 65536;
type Entry = { controller: AbortController; promise: Promise<Blob | null> };
const cache = new Map<string, Entry>();
onRichContentOwnerChange(() => { cache.forEach(entry => entry.controller.abort()); cache.clear(); });
function publicUrl(value: string) {
  try {
    const url = new URL(value);
    if (value.length > 500 || url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.port || url.origin === location.origin) return null;
    if (!/^[a-z\d.-]+\.[a-z]{2,}$/i.test(url.hostname) || /(?:^|\.)(?:localhost|local|internal|test|invalid)$/i.test(url.hostname)) return null;
    return url.href;
  } catch { return null; }
}
function load(url: string) {
  const existing = cache.get(url);
  if (existing) { cache.delete(url); cache.set(url, existing); return existing.promise; }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  const promise = (async () => {
    const response = await fetch(url, { credentials: 'omit', referrerPolicy: 'no-referrer', redirect: 'error', cache: 'force-cache', signal: controller.signal });
    const mime = response.headers.get('content-type')?.split(';')[0].trim().toLowerCase();
    if (!response.ok || !mime || !/^image\/(?:svg\+xml|png|jpeg|webp|avif|gif)$/.test(mime) || Number(response.headers.get('content-length')) > LIMIT || !response.body) { await response.body?.cancel(); return null; }
    const reader = response.body.getReader(); const chunks: Uint8Array<ArrayBuffer>[] = []; let size = 0;
    while (true) { const { done, value } = await reader.read(); if (done) break; size += value.length; if (size > LIMIT) { await reader.cancel(); return null; } chunks.push(new Uint8Array(value)); }
    return new Blob(chunks, { type: mime });
  })().catch(() => null).finally(() => clearTimeout(timer));
  cache.set(url, { controller, promise });
  if (cache.size > 32) { const first = cache.keys().next().value!; cache.get(first)?.controller.abort(); cache.delete(first); }
  return promise;
}
function pathData(value: string, viewBox: string) {
  if (value.length > 4096 || !/^[Mm][\d\s.,+-][MmZzLlHhVvCcSsQqTtAa\dEe\s.,+-]*$/.test(value) || (value.match(/[MmZzLlHhVvCcSsQqTtAa]/g)?.length ?? 0) > 256) return false;
  const box = viewBox.trim().split(/[\s,]+/).map(Number);
  if (box.length !== 4 || box.some(n => !Number.isFinite(n) || Math.abs(n) > 8192) || box[2] <= 0 || box[3] <= 0) return false;
  if ([...value.matchAll(/[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?/g)].some(match => !Number.isFinite(Number(match[0])) || Math.abs(Number(match[0])) > 8192)) return false;
  // Path2D silently truncates some malformed paths; check command arity too.
  const arity: Record<string, number> = { m: 2, l: 2, h: 1, v: 1, c: 6, s: 4, q: 4, t: 2, a: 7, z: 0 };
  for (const command of value.matchAll(/([MmZzLlHhVvCcSsQqTtAa])([^MmZzLlHhVvCcSsQqTtAa]*)/g)) {
    const numbers = (command[2].match(/[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g) ?? []).map(Number);
    const count = numbers.length;
    const size = arity[command[1].toLowerCase()];
    if (size === 0 ? count !== 0 : count === 0 || count % size !== 0) return false;
    if (command[1].toLowerCase() === 'a') for (let i = 0; i < count; i += 7) {
      if (numbers[i] < 0 || numbers[i + 1] < 0 || ![0, 1].includes(numbers[i + 3]) || ![0, 1].includes(numbers[i + 4])) return false;
    }
  }
  try { new Path2D(value); return true; } catch { return false; }
}
export default function IconAsset({ input, viewBox = '0 0 24 24', variant }: { input: string; viewBox?: string; variant?: string }) {
  const ref = useRef<HTMLSpanElement>(null); const [visible, setVisible] = useState(false);
  const pathRef = useRef<SVGPathElement>(null);
  const [image, setImage] = useState<{ key: string; url: string }>(); const [failed, setFailed] = useState(false);
  const url = useMemo(() => publicUrl(input), [input]);
  const path = useMemo(() => !url && pathData(input, viewBox), [input, url, viewBox]);
  const outline = variant === 'outline' || !variant && !/[Zz]/.test(input);
  useEffect(() => {
    if (!path || !pathRef.current) return;
    try {
      const bounds = pathRef.current.getBBox(); const [x, y, width, height] = viewBox.trim().split(/[\s,]+/).map(Number);
      if (!(bounds.width || bounds.height) || bounds.x + bounds.width < x || bounds.y + bounds.height < y || bounds.x > x + width || bounds.y > y + height) setFailed(true);
    } catch { setFailed(true); }
  }, [path, viewBox]);
  useEffect(() => { if (url && ref.current && !visible) return observeVisible(ref.current, () => setVisible(true)); }, [url, visible]);
  useEffect(() => {
    if (!url || !visible) return;
    let active = true; let objectUrl: string | undefined; const generation = diagramCacheGeneration();
    void load(url).then(blob => { if (!active || generation !== diagramCacheGeneration() || !blob) return; objectUrl = URL.createObjectURL(blob); setImage({ key: input, url: objectUrl }); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url, visible, input]);
  if (path && !failed) return <svg viewBox={viewBox} width="1em" height="1em" aria-hidden="true"><path ref={pathRef} d={input} fill={outline ? 'none' : 'currentColor'} stroke={outline ? 'currentColor' : undefined} strokeWidth={outline ? 1.75 : undefined} /></svg>;
  return <span ref={ref} className="rich-icon-asset">{!failed && image?.key === input ? <img src={image.url} alt="" aria-hidden="true" decoding="async" onError={() => setFailed(true)} /> : <span className="rich-icon-placeholder" />}</span>;
}
