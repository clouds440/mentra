import type { SourceChunk } from '../../types/rag';
import { fileLanguage, resolveLanguage } from '../../lib/codeLanguages';

export function passageLanguage(chunk: Pick<SourceChunk, 'spans' | 'media_type'>, filename?: string): string | undefined {
  const recorded = chunk.spans.find(span => span.language)?.language;
  if (recorded) return recorded;
  if (chunk.media_type?.startsWith('image/') || chunk.media_type === 'application/pdf' || chunk.media_type?.includes('officedocument')) return undefined;
  if (/\.html?$/i.test(filename ?? '') || chunk.spans.some(span => span.method.includes('ocr'))) return undefined;
  return fileLanguage(filename);
}
export function isMarkdown(language?: string) { return language && resolveLanguage(language).id === 'markdown'; }
export function groupPassages(chunks: SourceChunk[]): SourceChunk[] {
  const passages: SourceChunk[] = [];
  for (const chunk of chunks) {
    const previous = passages[passages.length - 1];
    const before = previous?.spans[previous.spans.length - 1];
    const after = chunk.spans[0];
    if (before && after && before.block === after.block && before.end === after.start
      && before.page === after.page && before.slide === after.slide && before.language === after.language
      && before.method === after.method && previous.heading_path.join('\0') === chunk.heading_path.join('\0')) {
      passages[passages.length - 1] = { ...previous, content: previous.content + chunk.content, spans: [...previous.spans, ...chunk.spans] };
    } else passages.push({ ...chunk });
  }
  return passages;
}
