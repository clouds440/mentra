import './prismSetup';
import 'prismjs/components/prism-core.js';
import type PrismType from 'prismjs';
import { languageDefinitions } from './codeLanguages';

const Prism = (globalThis as unknown as { Prism: typeof PrismType }).Prism;
Prism.manual = true;
// Bundled locally, loaded on demand: no CDN and no document text sent elsewhere.
const grammars = import.meta.glob(['/node_modules/prismjs/components/prism-*.js', '!/node_modules/prismjs/components/prism-*.min.js']);
const loading = new Map<string, Promise<void>>();
async function loadLanguage(id: string): Promise<void> {
  if (Prism.languages[id]) return;
  if (loading.has(id)) return loading.get(id);
  const load = (async () => {
    const definition = languageDefinitions[id];
    if (!definition || id === 'meta') return;
    for (const dependency of [definition.require ?? [], definition.modify ?? []].flat()) await loadLanguage(dependency);
    await grammars[`/node_modules/prismjs/components/prism-${id}.js`]?.();
  })().catch(error => { loading.delete(id); throw error; });
  loading.set(id, load);
  return load;
}
let queue = Promise.resolve();
self.onmessage = ({ data }: MessageEvent<{ id: number; code: string; language: string }>) => {
  queue = queue.then(async () => {
    try {
      await loadLanguage(data.language);
      if (data.language === 'markup') { await loadLanguage('css'); await loadLanguage('javascript'); }
      const grammar = Prism.languages[data.language];
      self.postMessage({ id: data.id, html: grammar ? Prism.highlight(data.code, grammar, data.language) : null });
    } catch { self.postMessage({ id: data.id, html: null }); }
  });
};
