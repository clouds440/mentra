import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkMath from 'remark-math';

interface MarkdownNode {
  type: string; value?: string; children?: MarkdownNode[]; data?: unknown;
  position?: { start: { offset?: number }; end: { offset?: number } };
}
const parser = unified().use(remarkParse).use(remarkMath);

/** Keep offsets stable for message-local citation plugins; never rewrite code. */
export function normalizeMathDelimiters(content: string): string {
  if (!content.includes('\\(') && !content.includes('\\[')) return content;
  const protectedRanges: [number, number][] = [];
  function visit(node: MarkdownNode) {
    if (['code', 'inlineCode', 'html', 'link', 'image', 'math', 'inlineMath'].includes(node.type)) {
      protectedRanges.push([node.position?.start.offset ?? 0, node.position?.end.offset ?? 0]);
    } else node.children?.forEach(visit);
  }
  visit(parser.parse(content) as MarkdownNode);
  return content.replace(/\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]/g, (match: string, inline: string | undefined, display: string | undefined, offset: number) => {
    const end = offset + match.length;
    if (protectedRanges.some(([start, stop]) => offset < stop && end > start)
      || (content.slice(0, offset).match(/\\+$/)?.[0].length ?? 0) % 2) return match;
    return inline === undefined ? `$$${display}$$` : `$ ${inline} $`;
  });
}

/** Common prose prices such as "$5 and $10" are not equations. */
export function remarkMathCurrency() {
  return (tree: MarkdownNode) => {
    function visit(node: MarkdownNode) {
      if (node.type === 'inlineMath' && /^\d[\d.,]*(?:\s*[–—-]\s*$|\s+(?:and|or|to|for|each|per|is|was|compared|instead)\b)/i.test(node.value ?? '')) {
        node.type = 'text'; node.value = `$${node.value}$`; delete node.data;
      }
      node.children?.forEach(visit);
    }
    visit(tree);
  };
}
