import { diagramCacheGeneration } from './richContentCache';

export type VisualFormat = 'svg' | 'png';
export const exportName = (title: string) => title.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '').slice(0, 80) || 'mentra-visual';

/** Local-only export: no model calls, remote fonts, screenshots or server uploads. */
export async function downloadVisual(source: string, format: VisualFormat, name: string) {
  const generation = diagramCacheGeneration();
  const documentSvg = new DOMParser().parseFromString(source, 'image/svg+xml');
  const svg = documentSvg.documentElement;
  if (svg.localName !== 'svg' || documentSvg.querySelector('parsererror')) throw new Error('Invalid export');
  const viewBox = svg.getAttribute('viewBox')?.split(/[\s,]+/).map(Number);
  const width = viewBox?.[2] || parseFloat(svg.getAttribute('width') ?? '');
  const height = viewBox?.[3] || parseFloat(svg.getAttribute('height') ?? '');
  if (!(width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height))) throw new Error('Invalid size');
  svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  svg.setAttribute('width', String(width)); svg.setAttribute('height', String(height));
  svg.removeAttribute('style');
  const background = documentSvg.createElementNS('http://www.w3.org/2000/svg', 'rect');
  background.setAttribute('x', String(viewBox?.[0] ?? 0)); background.setAttribute('y', String(viewBox?.[1] ?? 0));
  background.setAttribute('width', String(width)); background.setAttribute('height', String(height));
  background.setAttribute('fill', `rgb(${getComputedStyle(document.documentElement).getPropertyValue('--card').trim().split(/\s+/).join(',')})`);
  svg.insertBefore(background, svg.firstChild);
  const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml;charset=utf-8' });
  const objectUrl = URL.createObjectURL(blob);
  try {
    let output = blob;
    if (format === 'png') {
      const image = new Image();
      await new Promise<void>((resolve, reject) => { image.onload = () => resolve(); image.onerror = () => reject(new Error('Image export failed')); image.src = objectUrl; });
      const scale = Math.min(2, 4096 / width, 4096 / height, Math.sqrt(4_000_000 / (width * height)));
      const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(width * scale)); canvas.height = Math.max(1, Math.round(height * scale));
      const context = canvas.getContext('2d'); if (!context) throw new Error('Image export unavailable');
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      output = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Image export unavailable')), 'image/png'));
    }
    if (generation !== diagramCacheGeneration()) return;
    const downloadUrl = format === 'svg' ? objectUrl : URL.createObjectURL(output);
    const link = document.createElement('a'); link.href = downloadUrl; link.download = `${exportName(name)}.${format}`; link.click();
    setTimeout(() => { URL.revokeObjectURL(downloadUrl); }, 1000);
  } finally { setTimeout(() => URL.revokeObjectURL(objectUrl), 1000); }
}
