import assert from 'node:assert/strict';

const base = process.argv[2];
assert(base && /^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base), 'Supply the local test container URL');
const html = await fetch(base);
assert(html.ok);
assert.match(html.headers.get('cache-control'), /no-cache/);
const source = await html.text();
const asset = /src="(\/assets\/[^" ]+\.js)"/.exec(source)?.[1];
assert(asset, 'Production script should be content-hashed');
const javascript = await fetch(base + asset, { headers: { 'Accept-Encoding': 'gzip' } });
assert(javascript.ok);
assert.equal(javascript.headers.get('content-encoding'), 'gzip');
assert.match(javascript.headers.get('cache-control'), /max-age=31536000.*immutable/);
assert.match(javascript.headers.get('vary'), /Accept-Encoding/);
assert.equal((await fetch(base + '/assets/missing-renovation-test.js')).status, 404);
assert.equal((await fetch(base + '/library/new')).status, 200);
assert.match((await fetch(base + '/theme.js')).headers.get('cache-control'), /no-cache/);
console.log('Production serving verified: gzip, immutable hashed assets, fresh HTML/theme, asset 404 and SPA routing.');
