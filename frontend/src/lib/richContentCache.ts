import type { ChartSpec } from './chartSpec';
import { chartSourceLimit } from './chartLimits';
// Kept separate from lazy renderers so auth never loads visualization libraries.
const diagramCache = new Map<string, string>();
const chartCache = new Map<string, ChartSpec | null>();
let characters = 0;
let chartCharacters = 0;
let generation = 0;
let owner: string | null = null;
const ownerCleanups = new Set<() => void>();
export function onRichContentOwnerChange(cleanup: () => void) { ownerCleanups.add(cleanup); }
export function setRichContentOwner(next: string | null) {
  if (next === owner) return;
  diagramCache.clear(); chartCache.clear(); characters = 0; chartCharacters = 0; generation++; owner = next;
  ownerCleanups.forEach(cleanup => cleanup());
}
export function readChart(code: string) {
  const value = chartCache.get(code);
  if (value !== undefined) { chartCache.delete(code); chartCache.set(code, value); }
  return value;
}
export function cacheChart(code: string, spec: ChartSpec | null) {
  if (code.length > chartSourceLimit) return;
  if (chartCache.has(code)) chartCharacters -= code.length;
  chartCache.delete(code); chartCache.set(code, spec);
  chartCharacters += code.length;
  while (chartCache.size > 30 || chartCharacters > 2_000_000) {
    const oldest = chartCache.keys().next().value!;
    chartCharacters -= oldest.length; chartCache.delete(oldest);
  }
}
export const diagramCacheGeneration = () => generation;
export function readDiagram(key: string) {
  const value = diagramCache.get(key);
  if (value !== undefined) { diagramCache.delete(key); diagramCache.set(key, value); }
  return value;
}
export function cacheDiagram(key: string, svg: string) {
  characters -= diagramCache.get(key)?.length ?? 0;
  diagramCache.delete(key); diagramCache.set(key, svg); characters += svg.length;
  while (diagramCache.size > 30 || characters > 2_000_000) {
    const oldest = diagramCache.keys().next().value!;
    characters -= diagramCache.get(oldest)!.length; diagramCache.delete(oldest);
  }
}
