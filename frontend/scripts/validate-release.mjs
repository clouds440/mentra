// Release builds must never silently embed the local development API address.
import { isIP } from 'node:net';

function publicHost(hostname) {
  const host = hostname.replace(/^\[|\]$/g, '').toLowerCase();
  if (isIP(host) === 4) {
    const [a, b, c, d] = host.split('.').map(Number);
    return !(a === 0 || a === 10 || a === 127 || a >= 224
      || a === 169 && b === 254 || a === 172 && b >= 16 && b <= 31
      || a === 192 && (b === 168 || b === 0 && (c === 2 || c === 0 && d !== 9 && d !== 10))
      || a === 100 && b >= 64 && b <= 127
      || a === 198 && (b === 18 || b === 19 || b === 51 && c === 100)
      || a === 203 && b === 0 && c === 113);
  }
  if (isIP(host) === 6) return /^[23]/.test(host) && !/^2001:db8(?::|$)/.test(host);
  const domain = host.replace(/\.$/, '');
  return domain.length <= 253 && domain.includes('.')
    && domain.split('.').every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))
    && !/\.(localhost|invalid|example|test)$/.test(domain);
}

if (process.env.MENTRA_RELEASE === 'true') {
  const value = process.env.VITE_API_URL;
  let valid = false;
  try {
    const url = new URL(value);
    valid = url.protocol === 'https:' && !url.username && !url.password
      && !url.search && !url.hash && url.pathname === '/'
      && publicHost(url.hostname);
  } catch { /* Print a configuration name only; never dump environment values. */ }
  if (!valid) {
    console.error('VITE_API_URL: release builds require the actual public HTTPS API origin.');
    process.exit(1);
  }
}
