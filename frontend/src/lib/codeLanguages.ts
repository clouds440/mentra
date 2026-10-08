import components from 'prismjs/components.json';

interface LanguageDefinition { title: string; alias?: string | string[]; require?: string | string[]; modify?: string | string[] }
export const languageDefinitions = components.languages as unknown as Record<string, LanguageDefinition>;
const aliases: Record<string, string> = {
  'c++': 'cpp', 'c#': 'csharp', py: 'python', ts: 'typescript', js: 'javascript',
  rs: 'rust', rb: 'ruby', kt: 'kotlin', cs: 'csharp', sh: 'bash', ps1: 'powershell',
  bat: 'batch', clj: 'clojure', ex: 'elixir', erl: 'erlang', hs: 'haskell', ml: 'ocaml',
  fs: 'fsharp', pl: 'perl', jl: 'julia', f90: 'fortran', cob: 'cobol', vhd: 'vhdl',
  cu: 'cuda', ino: 'arduino', scm: 'scheme', gd: 'gdscript', hcl: 'hcl', tf: 'hcl',
  env: 'bash', makefile: 'makefile', conf: 'ini', gitignore: 'git', diff: 'diff',
  hpp: 'cpp', cc: 'cpp', cxx: 'cpp', h: 'c', pyi: 'python', pyw: 'python',
  mjs: 'javascript', cjs: 'javascript', mts: 'typescript', cts: 'typescript',
  yml: 'yaml', jsonc: 'json', jsonl: 'json', ipynb: 'json', tfvars: 'hcl',
  psm1: 'powershell', psd1: 'powershell', kts: 'kotlin', cfg: 'ini',
  vue: 'markup', svelte: 'markup', astro: 'markup', jsx: 'jsx', tsx: 'tsx',
  mdx: 'markdown', cshtml: 'cshtml', razor: 'cshtml', graphql: 'graphql', gql: 'graphql',
};
for (const [id, definition] of Object.entries(languageDefinitions)) {
  if (id === 'meta') continue;
  for (const alias of [definition.alias ?? []].flat()) aliases[alias] = id;
}

export function resolveLanguage(value?: string): { id: string; label: string } {
  const hint = (value ?? '').toLowerCase().replace(/^language-/, '').replace(/^\./, '').split(/\s/)[0].slice(0, 48);
  const id = aliases[hint] ?? hint;
  const definition = id !== 'meta' ? languageDefinitions[id] : undefined;
  return { id: definition ? id : 'plain', label: definition?.title ?? (hint && !['plain', 'plaintext', 'text', 'none'].includes(hint) ? hint.toUpperCase() : 'Code') };
}

export function fileLanguage(filename?: string): string | undefined {
  if (!filename) return undefined;
  const name = filename.replace(/\\/g, '/').split('/').pop()!.toLowerCase();
  const named: Record<string, string> = { dockerfile: 'docker', containerfile: 'docker', makefile: 'makefile', gnumakefile: 'makefile', 'cmakelists.txt': 'cmake', jenkinsfile: 'groovy', gemfile: 'ruby', rakefile: 'ruby', vagrantfile: 'ruby', '.env': 'bash', '.gitignore': 'git', '.dockerignore': 'git', '.editorconfig': 'ini', '.npmrc': 'ini', '.bashrc': 'bash', '.zshrc': 'bash', readme: 'markdown', license: 'plain' };
  if (named[name]) return named[name];
  if (/^(dockerfile|containerfile)\./.test(name)) return 'docker';
  if (name.startsWith('.env.')) return 'bash';
  const extension = name.includes('.') ? name.split('.').pop()! : '';
  if (['txt', 'pdf', 'docx', 'pptx', 'png', 'jpg', 'jpeg'].includes(extension)) return undefined;
  return extension || undefined;
}
