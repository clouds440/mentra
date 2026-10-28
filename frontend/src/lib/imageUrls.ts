/** Public image locations only; never let response markup target local services. */
export function publicImageUrl(value: string, allowQuery = false) {
  try {
    const url = new URL(value);
    if (value.length > (allowQuery ? 2000 : 500) || url.protocol !== 'https:' || url.username || url.password || !allowQuery && url.search || url.hash || url.port || url.origin === location.origin) return null;
    if (!/^[a-z\d.-]+\.[a-z]{2,}$/i.test(url.hostname) || /(?:^|\.)(?:localhost|local|internal|test|invalid)$/i.test(url.hostname)) return null;
    return url.href;
  } catch { return null; }
}
