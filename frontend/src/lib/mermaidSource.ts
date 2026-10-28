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
