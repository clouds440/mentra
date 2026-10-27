// Kept separate from the lazy diagram renderer so auth never loads Mermaid.
const diagramCache = new Map<string, string>();
let characters = 0;
let generation = 0;
let owner: string | null = null;
export function setRichContentOwner(next: string | null) {
  if (next === owner) return;
  diagramCache.clear(); characters = 0; generation++; owner = next;
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
