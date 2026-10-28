import type { Root, RootContent } from 'mdast';
import type { Node } from 'unist';

export const colorTones = ['success', 'warning', 'danger', 'info', 'accent'] as const;
type DirectiveNode = Node & { name?: string; attributes?: Record<string, string | null | undefined>; children?: RootContent[]; data?: { hName?: string; hProperties?: Record<string, unknown> } };
const only = (attributes: Record<string, unknown>, keys: string[]) => Object.keys(attributes).every(key => keys.includes(key));
export const usesRichDirectives = (content: string) => /:(?:color|icon)\[|:{2,3}(?:bar|progress|details|callout)[{\s[]/.test(content);

/** Recognize a tiny vocabulary; never spread model attributes into DOM props. */
export function remarkRichContent() {
  return (tree: Root, file: { value: unknown }) => {
    let diagrams = 0;
    let charts = 0;
    let icons = 0;
    const containsImage = (node: RootContent): boolean => node.type === 'image' || 'children' in node && node.children.some(child => containsImage(child as RootContent));
    function visit(parent: { children?: RootContent[] }) {
      parent.children = parent.children?.map(child => {
        const node = child as DirectiveNode;
        if (child.type === 'paragraph' && containsImage(child)) child.data = { ...child.data, hName: 'div' };
        // A linked image retains its source link in the caption; avoid nested
        // interactive elements when the image itself opens the viewer.
        if (child.type === 'link' && child.children.length === 1 && child.children[0].type === 'image') {
          const image = child.children[0];
          node.data = { hName: 'mentra-image', hProperties: { src: image.url, alt: image.alt ?? '', label: image.title || image.alt || 'Image', source: child.url } };
          node.children = []; return child;
        }
        if (child.type === 'image') { child.data = { hName: 'mentra-image', hProperties: { src: child.url, alt: child.alt ?? '', label: child.title || child.alt || 'Image' } }; return child; }
        if (child.type === 'code' && child.lang?.toLowerCase() === 'mermaid' && ++diagrams > 3) child.lang = 'text';
        if (child.type === 'code' && child.lang?.toLowerCase() === 'recharts' && ++charts > 3) child.lang = 'text';
        if (!['textDirective', 'leafDirective', 'containerDirective'].includes(node.type)) { if ('children' in child) visit(child); return child; }
        const a = node.attributes ?? {};
        let props: Record<string, unknown> | undefined;
        let name: string | undefined;
        if (node.type === 'textDirective' && node.name === 'icon') {
          const value = node.children?.map(item => item.type === 'text' ? item.value : item.type === 'link' ? item.url : '').join('') ?? '';
          const valid = /^[A-Za-z][A-Za-z0-9-]{0,63}$/.test(value) || /^https:\/\//.test(value) && value.length <= 500 || /^[Mm][\d\s.,+-]/.test(value) && value.length <= 4096;
          name = 'mentra-icon'; props = { name: ++icons <= 32 && valid && only(a, ['viewBox', 'variant']) ? value : '', viewBox: a.viewBox ?? '0 0 24 24', variant: ['outline', 'solid'].includes(a.variant ?? '') ? a.variant : undefined };
        } else if (node.type === 'textDirective' && node.name === 'color' && only(a, ['tone', 'hex']) && (!!a.tone !== !!a.hex)) {
          const aliases: Record<string, string> = { green: 'success', red: 'danger', amber: 'warning', blue: 'info', purple: 'accent' };
          const tone = aliases[a.tone ?? ''] ?? a.tone;
          if (tone && colorTones.includes(tone as typeof colorTones[number])) props = { tone };
          if (a.hex && /^#[\da-fA-F]{6}$/.test(a.hex)) props = { hex: a.hex };
          if (props) { name = 'mentra-color'; visit(node); }
        } else if (node.type === 'leafDirective' && ['bar', 'progress'].includes(node.name ?? '') && only(a, ['label', 'value', 'max', 'unit'])) {
          const value = Number(a.value); const max = Number(a.max);
          if (a.label?.trim() && a.label.length <= 120 && a.value?.trim() && a.max?.trim() && Number.isFinite(value) && Number.isFinite(max) && value >= 0 && max > 0 && value <= max && (a.unit?.length ?? 0) <= 40) {
            name = 'mentra-bar'; props = { label: a.label.trim(), value, max, unit: a.unit ?? '' };
          }
        } else if (node.type === 'containerDirective' && ['details', 'callout'].includes(node.name ?? '') && only(a, ['title', 'tone']) && a.title && a.title.length <= 120) {
          if (node.name === 'details' || !a.tone || colorTones.includes(a.tone as typeof colorTones[number])) { name = `mentra-${node.name}`; props = { title: a.title, tone: a.tone ?? 'info' }; visit(node); }
        }
        if (name) { node.data = { hName: name, hProperties: props }; return child; }
        const start = node.position?.start.offset; const end = node.position?.end.offset;
        // Preserve malformed/unknown syntax instead of silently deleting it.
        return { type: 'text', value: typeof start === 'number' && typeof end === 'number' ? String(file.value).slice(start, end) : node.children?.map(item => 'value' in item ? item.value : '').join('') ?? '' } as RootContent;
      });
    }
    visit(tree);
  };
}
