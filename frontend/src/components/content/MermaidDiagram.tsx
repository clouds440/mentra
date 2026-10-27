import DOMPurify from 'dompurify';
import { useEffect, useId, useMemo, useState } from 'react';
import { Button, Dialog } from '../ui';
import { CodeBlock } from './CodeBlock';
import { useResolvedTheme } from '../theme/resolvedTheme';
import { cacheDiagram, diagramCacheGeneration, readDiagram } from '../../lib/richContentCache';
import { readableColor } from './ColorText';

let queue: Promise<unknown> = Promise.resolve();
let serial = 0;
function normalizedCss(value: string) {
  return value.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\\([\da-fA-F]{1,6})(?:\s)?|\\([^\n\r])/g,
    (_match, hex: string | undefined, escaped: string | undefined) => hex ? String.fromCodePoint(Math.min(parseInt(hex, 16), 0x10ffff)) : escaped ?? '');
}
function safeCss(value: string) {
  const normalized = normalizedCss(value);
  return !/@import|@font-face|image-set\s*\(/i.test(normalized) && [...normalized.matchAll(/url\s*\(\s*(['"]?)(.*?)\1\s*\)/gi)].every(match => /^#[\w-]+$/.test(match[2]));
}
function safeSource(code: string) {
  const normalized = normalizedCss(code);
  // Labels such as "Data: TanStack Query" are prose, not data URIs.
  if (code.length > 12000 || /%%\s*\{|^\s*---|(?:^|[;\n])\s*click\b|<\s*[a-z!/]|https?:\/\/|data:(?:[\w.+-]+\/[\w.+-]+)?(?:;[\w=.+-]+)*,|javascript:|file:\/\/|url\s*\(|image-set\s*\(|@\s*\{/im.test(normalized)) return false;
  return [...normalized.matchAll(/(?:^|[;\n])\s*(?:style|classDef|linkStyle)\s+[^\s;]+\s+([^;\n]+)/gim)].every(match => match[1].split(',').every(declaration => {
    const [property, value, ...extra] = declaration.trim().split(':');
    if (extra.length || !value) return false;
    if (['fill', 'stroke', 'color'].includes(property)) return /^(?:#[\da-f]{6}|none|transparent|white|black|red|blue|green|purple|orange|gray)$/i.test(value.trim());
    return property === 'stroke-width' && /^(?:[0-5](?:\.\d)?|6)(?:px)?$/.test(value.trim());
  }));
}
function namespaceSvg(raw: string, prefix: string) {
  if (raw.length > 1_000_000) throw new Error('Diagram exceeds its rendering budget');
  const clean = DOMPurify.sanitize(raw, { USE_PROFILES: { svg: true, svgFilters: true }, FORBID_TAGS: ['foreignObject', 'image', 'a', 'script', 'animate', 'set'], FORBID_ATTR: ['onload', 'onclick'] });
  const doc = new DOMParser().parseFromString(clean, 'image/svg+xml'); const svg = doc.documentElement;
  if (svg.tagName.toLowerCase() !== 'svg') throw new Error('Invalid diagram');
  const ids = new Map<string, string>();
  svg.querySelectorAll('[id]').forEach(node => { const id = node.id; ids.set(id, `${prefix}-${id}`); });
  if (svg.id) ids.set(svg.id, `${prefix}-${svg.id}`);
  const rewriteCss = (value: string) => value.replace(/url\(\s*(['"]?)#([^\s)'"]+)\1\s*\)|#([a-zA-Z_][\w-]*)/g,
    (match, _quote: string, reference: string | undefined, selector: string | undefined) => {
      const replacement = ids.get(reference ?? selector ?? '');
      return replacement ? reference ? `url(#${replacement})` : `#${replacement}` : match;
    });
  for (const node of [svg, ...svg.querySelectorAll('*')]) {
    for (const attr of [...node.attributes]) {
      if (/^(?:href|xlink:href)$/i.test(attr.name) && !attr.value.startsWith('#')) { node.removeAttribute(attr.name); continue; }
      let value = attr.value;
      if (!safeCss(value)) throw new Error('Unsupported diagram style');
      if (attr.name === 'id') value = ids.get(value) ?? value;
      else if (attr.name === 'aria-labelledby' || attr.name === 'aria-describedby') value = value.split(' ').map(id => ids.get(id) ?? id).join(' ');
      else if (/^(?:href|xlink:href)$/i.test(attr.name)) value = ids.has(value.slice(1)) ? `#${ids.get(value.slice(1))}` : value;
      else value = rewriteCss(value);
      node.setAttribute(attr.name, value);
    }
    if (node.tagName.toLowerCase() === 'style') {
      if (!safeCss(node.textContent ?? '')) throw new Error('Unsupported diagram stylesheet');
      node.textContent = rewriteCss(node.textContent ?? '');
    }
  }
  svg.setAttribute('role', 'img');
  if (!svg.getAttribute('aria-labelledby')) svg.setAttribute('aria-label', 'Explanation diagram');
  return new XMLSerializer().serializeToString(svg);
}
function styledSource(code: string, dark: boolean) {
  const names: Record<string, string> = { white: '#ffffff', black: '#000000', red: '#ff0000', blue: '#0000ff', green: '#008000', purple: '#800080', orange: '#ffa500', gray: '#808080' };
  return code.replace(/((?:^|[;\n])\s*(?:style|classDef)\s+[^\s;]+\s+)([^;\n]+)/gim, (_match, prefix: string, declarations: string) => {
    const pairs = declarations.split(',').map(item => item.trim().split(':').map(part => part.trim()));
    const fill = pairs.find(([key]) => key === 'fill')?.[1];
    const background = names[fill ?? ''] ?? fill;
    if (!background || !/^#[\da-f]{6}$/i.test(background)) return prefix + declarations;
    const requested = pairs.find(([key]) => key === 'color')?.[1];
    const foreground = names[requested ?? ''] ?? (requested && /^#[\da-f]{6}$/i.test(requested) ? requested : dark ? '#ffffff' : '#000000');
    const adjusted = readableColor(foreground, [1, 3, 5].map(index => parseInt(background.slice(index, index + 2), 16)));
    const hex = adjusted.startsWith('#') ? adjusted : '#' + (adjusted.match(/\d+/g) ?? []).map(value => Number(value).toString(16).padStart(2, '0')).join('');
    return prefix + [...pairs.filter(([key]) => key !== 'color').map(pair => pair.join(':')), `color:${hex}`].join(',');
  });
}

export function MermaidDiagram({ code }: { code: string }) {
  const id = useId().replace(/[^a-z0-9]/gi, ''); const theme = useResolvedTheme();
  const [rendered, setRendered] = useState<{ key: string; svg: string }>();
  const [errorKey, setErrorKey] = useState(''); const [source, setSource] = useState(false); const [expanded, setExpanded] = useState(false);
  const [downloading, setDownloading] = useState<'svg' | 'png'>(); const [downloadError, setDownloadError] = useState(false);
  const key = `${theme}:${code}`;
  useEffect(() => {
    let active = true;
    const generation = diagramCacheGeneration();
    const current = () => active && generation === diagramCacheGeneration();
    if (!safeSource(code)) { setErrorKey(key); return; }
    const task = async () => {
      if (!current()) return;
      try {
        let raw = readDiagram(key);
        if (!raw) {
          // Only uncached layout yields; a cached diagram needs no idle delay.
          await new Promise<void>(resolve => {
            if ('requestIdleCallback' in window) window.requestIdleCallback(() => resolve(), { timeout: 200 });
            else requestAnimationFrame(() => setTimeout(resolve, 0));
          });
          if (!current()) return;
          const { default: mermaid } = await import('mermaid');
          if (!current()) return;
          const styles = getComputedStyle(document.documentElement);
          const color = (name: string) => `rgb(${styles.getPropertyValue(`--${name}`).trim().split(/\s+/).join(',')})`;
          mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: theme === 'dark' ? 'dark' : 'default', suppressErrorRendering: true,
            // Current renderers read the global flag; the flowchart flag alone
            // leaves labels in foreignObject, which our SVG sanitizer removes.
            maxTextSize: 12000, maxEdges: 120, htmlLabels: false, flowchart: { htmlLabels: false },
            themeVariables: { fontFamily: 'system-ui, sans-serif', fontSize: '15px', primaryTextColor: color('foreground'), lineColor: color('muted') } });
          raw = (await mermaid.render(`mentraDiagram${++serial}`, styledSource(code, theme === 'dark'))).svg;
          if (!current()) return;
        }
        const svg = namespaceSvg(raw, id);
        if (current()) { cacheDiagram(key, raw); setErrorKey(''); setRendered({ key, svg }); }
      } catch { if (current()) setErrorKey(key); }
    };
    queue = queue.catch(() => {}).then(task);
    return () => { active = false; };
  }, [code, theme, key, id]);
  const svg = rendered?.key === key ? rendered.svg : undefined;
  const expandedSvg = useMemo(() => expanded && svg ? namespaceSvg(svg, `${id}-expanded`) : undefined, [expanded, svg, id]);
  async function download(format: 'svg' | 'png') {
    if (!svg || downloading) return;
    const generation = diagramCacheGeneration();
    setDownloading(format); setDownloadError(false);
    try { const { downloadVisual } = await import('../../lib/visualExport'); if (generation === diagramCacheGeneration()) await downloadVisual(svg, format, 'mentra-diagram'); }
    catch { setDownloadError(true); } finally { setDownloading(undefined); }
  }
  const figure = (content = svg) => content ? <div className="mermaid-svg overflow-x-auto p-3" tabIndex={0} role="region" aria-label="Diagram" dangerouslySetInnerHTML={{ __html: content }} /> : <p role="status" className="p-4 text-sm text-muted">{errorKey === key ? 'This diagram could not be displayed. View its source below.' : 'Preparing diagram…'}</p>;
  return <figure className="mermaid-figure my-4 overflow-hidden rounded-panel border border-border bg-card">
    <figcaption className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2 text-xs text-muted"><span>Diagram</span><span className="flex flex-wrap gap-1">
      <Button size="sm" variant="ghost" aria-pressed={source} onClick={() => setSource(value => !value)}>{source ? 'Show diagram' : 'View source'}</Button>
      <Button size="sm" variant="ghost" disabled={!svg} onClick={() => setExpanded(true)}>Expand</Button>
      <Button size="sm" variant="ghost" disabled={!svg || !!downloading} loading={downloading === 'svg'} onClick={() => void download('svg')}>Download SVG</Button>
      <Button size="sm" variant="ghost" disabled={!svg || !!downloading} loading={downloading === 'png'} onClick={() => void download('png')}>Download PNG</Button>
    </span></figcaption>
    {errorKey === key && <p role="status" className="px-3 pt-3 text-sm text-muted">This diagram could not be displayed. Its source is available below.</p>}
    {downloadError && <p role="status" className="px-3 pt-3 text-sm text-muted">Could not download this diagram. Please try again.</p>}
    {source || errorKey === key ? <CodeBlock code={code} language="mermaid" /> : figure()}
    {expanded && <Dialog open onDismiss={() => setExpanded(false)} aria-label="Expanded diagram" className="mermaid-fullscreen"><div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2"><span className="text-sm text-muted">Diagram</span><Button variant="ghost" onClick={() => setExpanded(false)}>Close</Button></div>{figure(expandedSvg)}</Dialog>}
  </figure>;
}
