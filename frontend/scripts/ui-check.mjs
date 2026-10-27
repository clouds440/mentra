import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../src/styles/global.css', import.meta.url), 'utf8');
assert(!/html\[data-theme-ready\]\s*\*/.test(css), 'Do not add transitions to every element');
const light = css.slice(css.indexOf(':root {'), css.indexOf(":root[data-theme='dark']"));
const dark = css.slice(css.indexOf(":root[data-theme='dark']"), css.indexOf('/* Motion'));
const luminance = rgb => rgb.map(value => { const channel = value / 255; return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4; }).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
const contrast = (first, second) => { const [high, low] = [luminance(first), luminance(second)].sort((a, b) => b - a); return (high + .05) / (low + .05); };
for (const [name, block] of [['light', light], ['dark', dark]]) {
  const tokens = Object.fromEntries([...block.matchAll(/--([a-z-]+): (\d+) (\d+) (\d+);/g)].map(match => [match[1], match.slice(2).map(Number)]));
  for (const text of ['foreground', 'heading', 'body', 'muted', 'subtle']) for (const surface of ['background', 'card', 'surface', 'input', 'popover']) {
    assert(contrast(tokens[text], tokens[surface]) >= 4.5, `${name}: ${text} on ${surface} needs 4.5:1 contrast`);
  }
  for (const text of ['rich-success', 'rich-warning', 'rich-danger', 'rich-accent']) for (const surface of ['background', 'card', 'surface', 'input', 'popover', 'message']) {
    assert(contrast(tokens[text], tokens[surface]) >= 4.5, `${name}: ${text} on ${surface} needs 4.5:1 contrast`);
  }
  assert(contrast(tokens['border-strong'], tokens.input) >= 3, `${name}: input boundary needs 3:1 contrast`);
  assert(contrast(tokens['accent-foreground'], tokens.primary) >= 4.5, `${name}: primary action text needs 4.5:1 contrast`);
}
console.log('UI checks passed: explicit transitions, both text palettes, input boundaries and primary actions.');
