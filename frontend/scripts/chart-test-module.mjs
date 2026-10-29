import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText;
const modules = new Map();
export async function moduleUrl(name) {
  if (modules.has(name)) return modules.get(name);
  let output = compile(await readFile(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8'));
  for (const match of [...output.matchAll(/from ['"]\.\/([^'"]+)['"]/g)]) output = output.replace(match[0], `from ${JSON.stringify(await moduleUrl(match[1]))}`);
  const url = `data:text/javascript;base64,${Buffer.from(output).toString('base64')}`;
  modules.set(name, url); return url;
}
