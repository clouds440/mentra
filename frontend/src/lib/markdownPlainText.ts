import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { normalizeMathDelimiters, remarkMathCurrency } from './mathMarkdown';
import remarkDirective from 'remark-directive';
import { remarkRichContent } from './richMarkdown';
import { valueText } from '../components/ui/ProgressBar';

interface Node { type: string; value?: string; url?: string; alt?: string; children?: Node[]; ordered?: boolean; start?: number; name?: string; attributes?: Record<string, string> }
const parser = unified().use(remarkParse).use(remarkGfm).use(remarkMath).use(remarkMathCurrency).use(remarkDirective).use(remarkRichContent);

// Parse Markdown rather than stripping punctuation: code, escaped characters,
// nested formatting, tables and link labels retain their actual content.
export function markdownPlainText(markdown: string): string {
  function text(node: Node): string {
    const children = node.children ?? [];
    switch (node.type) {
      case 'root': return children.map(text).join('\n\n');
      case 'text': case 'inlineCode': case 'code': return node.value ?? '';
      case 'inlineMath': return `$${node.value?.trim() ?? ''}$`;
      case 'math': return `$$\n${node.value ?? ''}\n$$`;
      case 'break': return '\n';
      case 'textDirective': return children.map(text).join('');
      case 'leafDirective': return `${node.attributes?.label}: ${valueText(Number(node.attributes?.value), Number(node.attributes?.max), node.attributes?.unit)}`;
      case 'containerDirective': return `${node.attributes?.title}\n${children.map(text).join('\n\n')}`;
      case 'html': return '';
      case 'image': return node.alt ?? '';
      case 'link': return children.map(text).join('') + (node.url && !node.url.startsWith('#') ? ` (${node.url})` : '');
      case 'list': return children.map((child, index) => `${node.ordered ? `${(node.start ?? 1) + index}.` : '•'} ${text(child)}`).join('\n');
      case 'listItem': case 'blockquote': return children.map(text).join('\n');
      case 'table': return children.map(text).join('\n');
      case 'tableRow': return children.map(text).join('\t');
      case 'thematicBreak': return '';
      default: return children.map(text).join('');
    }
  }
  const normalized = normalizeMathDelimiters(markdown);
  const tree = parser.parse(normalized);
  return text(parser.runSync(tree, normalized) as Node).trim();
}
