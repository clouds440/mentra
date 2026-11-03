import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { execFileSync } from 'node:child_process';

const source = process.env.AUDIT_CACHE_BASELINE === '1'
  ? execFileSync('git', ['show', 'c3f0537:frontend/src/services/pageCache.ts'], { encoding: 'utf8' })
  : readFileSync(new URL('../src/services/pageCache.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const sandbox = { exports: {}, require: () => ({ openBroadcastChannel: () => null }), AbortController, DOMException, Date, Promise, setTimeout, clearTimeout };
vm.runInNewContext(code, sandbox);
const cache = sandbox.exports;
cache.setPageCacheOwner('owner');
let loads = 0;
const load = async () => ({ jobs: [{ state: 'FAILED' }], sequence: ++loads });
await cache.cachedPage('/api/v1/documents/doc[]', load);
cache.invalidateMutation('/api/v1/rag/jobs/job/retry');
await cache.cachedPage('/api/v1/documents/doc[]', load);
assert.equal(loads, 2, 'A successful RAG retry must fetch fresh document state');
cache.invalidateMutation('/api/v1/documents/doc/reindex');
await cache.cachedPage('/api/v1/documents/doc[]', load);
assert.equal(loads, 3);
console.log('Audit cache regressions passed.');
