/** Normalize presentation only; the renderer still validates and sanitizes. */
export function normalizeMermaidSource(source: string): string {
  if (source.length > 12000) return source;
  // Attribute-free break tags become plain whitespace, never executable HTML.
  const lines = source.replace(/<br\s*\/?\s*>/gi, ' ').split(/\r?\n/);
  let index = 0;
  while (index < lines.length && (!lines[index].trim() || /^\s*%%(?!\{)/.test(lines[index]))) index++;
  const start = index;
  while (index < lines.length && /^\s*acc(?:Title|Descr)\s*:/.test(lines[index])) index++;
  // Move only contiguous accessibility metadata before a flowchart declaration.
  if (index > start && /^\s*(?:flowchart|graph)\s+(?:TB|TD|BT|RL|LR)\s*;?\s*$/.test(lines[index] ?? '')) {
    const declaration = lines.splice(index, 1)[0];
    lines.splice(start, 0, declaration);
  }
  return lines.join('\n');
}

/** Accept structured titles and legacy Mermaid accessibility metadata. */
export function readMermaidSpec(code: string): { source: string; title?: string } {
  if (code.length <= 13000 && code.trimStart().startsWith('{')) {
    try {
      const value = JSON.parse(code);
      if (typeof value?.source === 'string' && value.source.length <= 12000) {
        const title = typeof value.title === 'string' && value.title.length <= 120 ? value.title.trim() : '';
        return { source: value.source, title: title || legacyTitle(value.source) };
      }
    } catch { /* Invalid JSON follows the normal source fallback. */ }
  }
  return { source: code, title: legacyTitle(code) };
}

function legacyTitle(source: string): string | undefined {
  if (source.length > 12000) return undefined;
  return /^[ \t]*accTitle:[ \t]*([^\r\n]+)/m.exec(source)?.[1].trim().slice(0, 120) || undefined;
}
