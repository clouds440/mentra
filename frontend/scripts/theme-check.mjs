import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const bootstrap = readFileSync(new URL('../public/theme.js', import.meta.url), 'utf8');
const provider = ts.transpileModule(readFileSync(new URL('../src/components/theme/ThemeProvider.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

function environment(saved, dark, blocked = false) {
  const root = { dataset: {}, style: {} };
  const mediaListeners = new Set();
  const storageListeners = new Set();
  const media = {
    matches: dark,
    addEventListener: (_, fn) => mediaListeners.add(fn),
    removeEventListener: (_, fn) => mediaListeners.delete(fn),
  };
  const storage = {
    getItem: () => { if (blocked) throw Error('blocked'); return saved; },
    setItem: (_, value) => { if (blocked) throw Error('blocked'); saved = value; },
  };
  let state;
  let effects = [];
  let cleanups = [];
  const exports = {};
  const context = vm.createContext({
    document: { documentElement: root }, localStorage: storage,
    matchMedia: () => media,
    window: { matchMedia: () => media, addEventListener: (_, fn) => storageListeners.add(fn), removeEventListener: (_, fn) => storageListeners.delete(fn) },
    requestAnimationFrame: () => 1, cancelAnimationFrame: () => {},
    exports,
    require: (name) => name === 'react/jsx-runtime' ? { jsx: (_, props) => props } : {
      createContext: () => ({ Provider: {} }),
      useState: (initial) => { if (state === undefined) state = initial(); return [state, (value) => { state = value; }]; },
      useEffect: (fn) => effects.push(fn),
    },
  });
  vm.runInContext(bootstrap, context);
  vm.runInContext(provider, context);
  function render() {
    cleanups.forEach((fn) => fn?.());
    effects = [];
    const result = exports.ThemeProvider({ children: null });
    cleanups = effects.map((fn) => fn());
    return result.value;
  }
  return { root, render, saved: () => saved,
    os: (next) => { media.matches = next; mediaListeners.forEach((fn) => fn()); },
    sync: (value) => storageListeners.forEach((fn) => fn({ key: 'mentra-theme', newValue: value, storageArea: storage })),
    cleanup: () => cleanups.forEach((fn) => fn?.()), mediaListeners, storageListeners,
  };
}

for (const [saved, dark, expected] of [
  [null, false, 'light'], [null, true, 'dark'], ['system', true, 'dark'],
  ['light', true, 'light'], ['dark', false, 'dark'], ['invalid', true, 'dark'],
]) {
  const app = environment(saved, dark);
  assert.equal(app.root.dataset.theme, expected, 'correct palette before React');
  app.render();
  assert.equal(app.root.dataset.theme, expected, 'React matches bootstrap');
  app.cleanup();
  assert.equal(app.mediaListeners.size, 0);
  assert.equal(app.storageListeners.size, 0);
}
const app = environment(null, false);
assert.equal(app.render().preference, 'system');
app.os(true);
assert.equal(app.root.dataset.theme, 'dark');
app.render().setPreference('light');
assert.equal(app.saved(), 'light');
app.render();
app.os(true);
assert.equal(app.root.dataset.theme, 'light', 'explicit preference ignores OS');
app.render().setPreference('system');
app.render();
assert.equal(app.root.dataset.theme, 'dark');
app.os(false);
assert.equal(app.root.dataset.theme, 'light');
app.sync('dark');
app.render();
assert.equal(app.root.dataset.theme, 'dark', 'cross-tab synchronization');
app.sync(null);
assert.equal(app.render().preference, 'system', 'removed storage restores System');
const blocked = environment(null, true, true);
blocked.render().setPreference('light');
blocked.render();
assert.equal(blocked.root.dataset.theme, 'light', 'blocked storage still allows switching');
console.log('Theme checks passed: bootstrap, System updates, explicit overrides, persistence, cross-tab sync, blocked storage, listener cleanup.');
