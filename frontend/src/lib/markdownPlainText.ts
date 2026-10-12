import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';

interface Node { type: string; value?: string; url?: string; alt?: string; children?: Node[]; ordered?: boolean; start?: number }
const parser = unified().use(remarkParse).use(remarkGfm);

// Parse Markdown rather than stripping punctuation: code, escaped characters,
// nested formatting, tables and link labels retain their actual content.
export function markdownPlainText(markdown: string): string {
  function text(node: Node): string {
    const children = node.children ?? [];
    switch (node.type) {
      case 'root': return children.map(text).join('\n\n');
      case 'text': case 'inlineCode': case 'code': return node.value ?? '';
      case 'break': return '\n';
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
  return text(parser.parse(markdown) as Node).trim();
}
