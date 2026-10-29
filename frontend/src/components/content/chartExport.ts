import { modelSummary } from '../../lib/chartModel';
import type { ChartSpec } from '../../lib/chartSpec';
import { plotColor } from './charts/shared';

const namespace = 'http://www.w3.org/2000/svg';
const properties = ['fill', 'stroke', 'fill-opacity', 'stroke-opacity', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity', 'font-size', 'font-weight', 'font-style', 'text-anchor', 'dominant-baseline', 'clip-path', 'stop-color', 'stop-opacity'];
const frame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));

/** Wait for layout/short chart animations, then copy actual SVG geometry. */
export async function exportChart(container: HTMLElement, spec: ChartSpec) {
  let svg: SVGSVGElement | null = null; let signature = ''; let stable = 0;
  const started = performance.now();
  while (performance.now() - started < 4000) {
    await frame();
    if (!container.isConnected) throw new Error('Chart viewer closed');
    svg = container.querySelector<SVGSVGElement>('.chart-plot .recharts-wrapper > svg.recharts-surface');
    if (!svg || !svg.querySelector('.recharts-layer')) continue;
    const next = svg.innerHTML;
    stable = next === signature ? stable + 1 : 0; signature = next;
    if (stable >= 3 && performance.now() - started > 300) break;
  }
  if (!svg || stable < 3) throw new Error('Chart is still loading');
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const originals = [svg, ...svg.querySelectorAll('*')]; const copies = [clone, ...clone.querySelectorAll('*')];
  originals.forEach((node, index) => {
    const target = copies[index]; const computed = getComputedStyle(node);
    target.removeAttribute('class'); target.removeAttribute('style');
    for (const property of properties) {
      let value = computed.getPropertyValue(property);
      value = value.replace(/url\(["']?[^)]*#([^)'"\s]+)["']?\)/g, 'url(#$1)');
      if (value && !/url\((?!#)/i.test(value)) (target as SVGElement).style.setProperty(property, value);
    }
    if (node.localName === 'text' || node.localName === 'tspan') (target as SVGElement).style.fontFamily = 'Arial, sans-serif';
    for (const attr of [...target.attributes]) if (/^on/i.test(attr.name) || attr.value.includes('var(') || /^(?:href|xlink:href)$/i.test(attr.name) && !attr.value.startsWith('#')) target.removeAttribute(attr.name);
  });
  clone.querySelectorAll('foreignObject,script,animate,set,style,image').forEach(node => node.remove());
  const width = Number(svg.getAttribute('width')) || svg.getBoundingClientRect().width;
  const height = Number(svg.getAttribute('height')) || svg.getBoundingClientRect().height;
  if (!(width > 0 && height > 0)) throw new Error('Chart has no size');
  const doc = document.implementation.createDocument(namespace, 'svg'); const root = doc.documentElement;
  const styles = getComputedStyle(document.documentElement);
  const foreground = `rgb(${styles.getPropertyValue('--foreground').trim().split(/\s+/).join(',')})`;
  const resolveColor = (color: string) => color.replace(/rgb\(var\(--([\w-]+)\)\)/g, (_match, token: string) => `rgb(${styles.getPropertyValue('--' + token).trim().split(/\s+/).join(',')})`);
  const context = document.createElement('canvas').getContext('2d');
  function text(value: string, x: number, y: number, size: number, bold = false) {
    const element = doc.createElementNS(namespace, 'text'); element.textContent = value;
    element.setAttribute('x', String(x)); element.setAttribute('y', String(y)); element.setAttribute('fill', foreground);
    element.setAttribute('font-family', 'Arial, sans-serif'); element.setAttribute('font-size', String(size));
    if (bold) element.setAttribute('font-weight', '600'); root.appendChild(element);
  }
  let cursor = 26;
  function wrapped(value: string, size: number, bold = false) {
    if (context) context.font = `${bold ? '600 ' : ''}${size}px Arial`;
    let line = '';
    for (const word of value.split(/\s+/)) {
      const measure = (text: string) => context?.measureText(text).width ?? text.length * size * .6;
      if (measure(word) > width - 32) {
        if (line) { text(line, 16, cursor, size, bold); cursor += size + 5; line = ''; }
        for (const character of word) {
          if (line && measure(line + character) > width - 32) { text(line, 16, cursor, size, bold); cursor += size + 5; line = ''; }
          line += character;
        }
        continue;
      }
      const candidate = line ? `${line} ${word}` : word;
      if (line && (context?.measureText(candidate).width ?? candidate.length * size * .6) > width - 32) { text(line, 16, cursor, size, bold); cursor += size + 5; line = word; } else line = candidate;
    }
    if (line) { text(line, 16, cursor, size, bold); cursor += size + 5; }
  }
  wrapped(spec.title, 18, true);
  if (spec.unit) wrapped(`Values in ${spec.unit}`, 12);
  if (spec.description) wrapped(spec.description, 12);
  if (spec.modelUnavailable) wrapped('Equation controls unavailable. Supplied data shown.', 12);
  if (spec.model) wrapped(modelSummary(spec.model), 12);
  const body = doc.createElementNS(namespace, 'g'); body.setAttribute('transform', `translate(0 ${cursor + 8})`);
  while (clone.firstChild) body.appendChild(doc.importNode(clone.firstChild, true)), clone.removeChild(clone.firstChild);
  root.appendChild(body); cursor += height + 22;
  const entries = spec.type === 'PieChart' ? spec.data.map((row, i) => ({ label: String(row[spec.xKey]), color: plotColor(spec, i, false) })) : spec.series.map((item, i) => ({ label: item.name, color: plotColor(spec, i) }));
  let x = 16;
  for (const entry of entries) {
    if (context) context.font = '12px Arial';
    const itemWidth = Math.min(width - 32, (context?.measureText(entry.label).width ?? entry.label.length * 7) + 32);
    if (x > 16 && x + itemWidth > width - 16) { cursor += 24; x = 16; }
    const swatch = doc.createElementNS(namespace, 'rect'); swatch.setAttribute('x', String(x)); swatch.setAttribute('y', String(cursor - 10)); swatch.setAttribute('width', '10'); swatch.setAttribute('height', '10'); swatch.setAttribute('fill', resolveColor(entry.color)); root.appendChild(swatch);
    text(entry.label, x + 16, cursor, 12); x += itemWidth;
  }
  root.setAttribute('viewBox', `0 0 ${width} ${cursor + 20}`); root.setAttribute('width', String(width)); root.setAttribute('height', String(cursor + 20)); root.setAttribute('role', 'img'); root.setAttribute('aria-label', spec.title);
  return new XMLSerializer().serializeToString(root);
}
