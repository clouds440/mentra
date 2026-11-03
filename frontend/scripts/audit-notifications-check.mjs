import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const calls = [], invalidations = [];
const api = { apiEvents: (path, signal, receive) => new Promise(resolve => {
  calls.push({ path, signal, receive }); signal.addEventListener('abort', resolve, { once: true });
}) };
const code = ts.transpileModule(readFileSync(new URL('../src/services/notifications.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const sandbox = { exports: {}, require: name => name === './api' ? api : { invalidatePageCache: (...args) => invalidations.push(args) },
  AbortController, setTimeout, clearTimeout, window: { dispatchEvent() {} } };
vm.runInNewContext(code, sandbox);
const received = [], second = [];
const close = sandbox.exports.watchNotifications('owner', value => received.push(value.unread_count));
const closeSecond = sandbox.exports.watchNotifications('owner', value => second.push(value.unread_count));
assert.equal(calls.length, 1, 'Multiple bells must share one stream');
calls[0].receive('notifications', { unread_count: 0, sync_revision: 0 });
calls[0].receive('notifications', { unread_count: 1, sync_revision: 1 });
assert.deepEqual(received, [0, 1]); assert.deepEqual(second, [0, 1]);
assert.equal(invalidations.length, 1, 'Background revision invalidates inbox');
close(); assert.equal(calls[0].signal.aborted, false);
closeSecond(); assert.equal(calls[0].signal.aborted, true);
calls[0].receive('notifications', { unread_count: 99, sync_revision: 2 });
assert.deepEqual(received, [0, 1], 'Late old-owner notifications are ignored');
console.log('Notification stream checks passed: revision delivery, shared connection, invalidation, cleanup, stale suppression.');
