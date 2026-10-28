import { Children, isValidElement, lazy, memo, useMemo, type ReactNode } from 'react';
import type { Element as HastElement } from 'hast';
import ReactMarkdown, { type Components, type Options } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { normalizeMathDelimiters, remarkMathCurrency } from '../../lib/mathMarkdown';
import { CodeBlock } from './CodeBlock';
import remarkDirective from 'remark-directive';
import { remarkRichContent, usesRichDirectives } from '../../lib/richMarkdown';
import { ColorText } from './ColorText';
import { InlineIcon } from './InlineIcon';
import { DeferredVisual } from './DeferredVisual';
import { ProgressBar } from '../ui/ProgressBar';
import { CaptionedImage } from './CaptionedImage';

const MermaidDiagram = lazy(() => import('./MermaidDiagram').then(module => ({ default: module.MermaidDiagram })));
const RechartsFigure = lazy(() => import('./RechartsFigure').then(module => ({ default: module.RechartsFigure })));
type RichProps = { node?: HastElement; children?: ReactNode };
type MarkdownProps = { content: string; linkComponent?: Components['a']; plugins?: Options['remarkPlugins'] };
const noPlugins: NonNullable<Options['remarkPlugins']> = [];

function MarkdownCode({ children }: { children?: ReactNode }) {
  const child = Children.toArray(children).find(isValidElement);
  if (!child) return <pre>{children}</pre>;
  const props = child.props as { children?: ReactNode; className?: string };
  const code = Children.toArray(props.children).join('').replace(/\n$/, '');
  const language = /language-([^\s]+)/.exec(props.className ?? '')?.[1];
  if (language?.toLowerCase() === 'mermaid') return <DeferredVisual code={code} kind="diagram"><MermaidDiagram code={code} /></DeferredVisual>;
  if (language?.toLowerCase() === 'recharts') return <DeferredVisual code={code} kind="chart"><RechartsFigure code={code} /></DeferredVisual>;
  return <CodeBlock code={code} language={language} />;
}
export const MarkdownContent = memo(function MarkdownContent(props: MarkdownProps) {
  // No AST, plugins, KaTeX work or extra component state for ordinary text.
  if (!props.plugins?.length && !/[\n\r\t\\`*_#\[\]<>{}|~$@&=:+-]/.test(props.content) && !/^(?: {4}| {0,3}\d+[.)]\s)|\bwww\./i.test(props.content)) return <div className="markdown-content"><p>{props.content}</p></div>;
  return <FormattedContent {...props} />;
});
MarkdownContent.displayName = 'MarkdownContent';

function FormattedContent({ content, linkComponent, plugins = noPlugins }: MarkdownProps) {
  const components = useMemo<Components>(() => ({
    pre: MarkdownCode,
    a: linkComponent ?? (({ children, href }) => <a href={href} rel="noopener noreferrer">{children}</a>),
    table: ({ children }) => <div className="markdown-table-scroll"><table>{children}</table></div>,
    'mentra-image': ({ node }: RichProps) => <CaptionedImage src={String(node?.properties.src ?? '')} alt={String(node?.properties.alt ?? '')} label={String(node?.properties.label ?? '')} source={node?.properties.source ? String(node.properties.source) : undefined} />,
    'mentra-icon': ({ node }: RichProps) => <InlineIcon name={String(node?.properties.name ?? '')} viewBox={String(node?.properties.viewBox ?? node?.properties.viewbox ?? '0 0 24 24')} variant={node?.properties.variant ? String(node.properties.variant) : undefined} />,
    'mentra-color': ({ node, children }: RichProps) => <ColorText tone={String(node?.properties.tone ?? '')} hex={node?.properties.hex ? String(node.properties.hex) : undefined}>{children}</ColorText>,
    'mentra-bar': ({ node }: RichProps) => <div className="my-4"><ProgressBar mode="meter" label={String(node?.properties.label ?? '')} value={Number(node?.properties.value)} max={Number(node?.properties.max)} unit={String(node?.properties.unit ?? '')} /></div>,
    'mentra-details': ({ node, children }: RichProps) => <details className="my-4 rounded-panel border border-border px-4 py-3"><summary className="ui-disclosure cursor-pointer font-medium text-heading">{String(node?.properties.title ?? 'Explanation')}</summary><div className="mt-2">{children}</div></details>,
    'mentra-callout': ({ node, children }: RichProps) => <aside className="rich-callout my-4 rounded-panel border border-border bg-surface p-4"><div className="font-medium"><ColorText tone={String(node?.properties.tone ?? 'info')}>{String(node?.properties.title ?? '')}</ColorText></div>{children}</aside>,
  }), [linkComponent]);
  const markdown = useMemo(() => normalizeMathDelimiters(content), [content]);
  const directives = usesRichDirectives(content);
  const diagrams = /(?:```|~~~)\s*(?:mermaid|recharts)/i.test(content);
  const images = /!\[/.test(content);
  const remarkPlugins = useMemo(() => [remarkGfm, remarkMath, remarkMathCurrency, ...(directives ? [remarkDirective] : []), ...(directives || diagrams || images ? [remarkRichContent] : []), ...(plugins ?? noPlugins)], [directives, diagrams, images, plugins]);
  return <div className="markdown-content"><ReactMarkdown remarkPlugins={remarkPlugins}
    rehypePlugins={[[rehypeKatex, { trust: false, maxExpand: 500, maxSize: 20, throwOnError: false }]]} components={components}>{markdown}</ReactMarkdown></div>;
}
