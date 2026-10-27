import { Children, Component, isValidElement, lazy, memo, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
import { ProgressBar } from '../ui/ProgressBar';

const MermaidDiagram = lazy(() => import('./MermaidDiagram').then(module => ({ default: module.MermaidDiagram })));
type RichProps = { node?: HastElement; children?: ReactNode };
type MarkdownProps = { content: string; linkComponent?: Components['a']; plugins?: Options['remarkPlugins'] };
const noPlugins: NonNullable<Options['remarkPlugins']> = [];

class DiagramBoundary extends Component<{ children: ReactNode; code: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="my-4"><p role="status" className="text-sm text-muted">This diagram could not be loaded. Its source is available below.</p><CodeBlock code={this.props.code} language="mermaid" /></div> : this.props.children;
  }
}

const waitingDiagrams = new Map<Element, () => void>();
let diagramObserver: IntersectionObserver | undefined;
function observeDiagram(element: HTMLElement, ready: () => void) {
  if (!('IntersectionObserver' in window)) { ready(); return () => {}; }
  diagramObserver ??= new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) { const notify = waitingDiagrams.get(entry.target); waitingDiagrams.delete(entry.target); diagramObserver?.unobserve(entry.target); notify?.(); }
    if (!waitingDiagrams.size) { diagramObserver?.disconnect(); diagramObserver = undefined; }
  }, { rootMargin: '300px' });
  waitingDiagrams.set(element, ready); diagramObserver.observe(element);
  return () => { waitingDiagrams.delete(element); diagramObserver?.unobserve(element); if (!waitingDiagrams.size) { diagramObserver?.disconnect(); diagramObserver = undefined; } };
}
function DiagramBlock({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null); const [visible, setVisible] = useState(false);
  useEffect(() => { if (ref.current && !visible) return observeDiagram(ref.current, () => setVisible(true)); }, [visible]);
  const placeholder = <div className="mermaid-placeholder my-4 rounded-panel border border-border p-4 text-sm text-muted" role="status">Diagram</div>;
  return <div ref={ref}>{visible ? <DiagramBoundary key={code} code={code}><Suspense fallback={placeholder}><MermaidDiagram code={code} /></Suspense></DiagramBoundary> : placeholder}</div>;
}

function MarkdownCode({ children }: { children?: ReactNode }) {
  const child = Children.toArray(children).find(isValidElement);
  if (!child) return <pre>{children}</pre>;
  const props = child.props as { children?: ReactNode; className?: string };
  const code = Children.toArray(props.children).join('').replace(/\n$/, '');
  const language = /language-([^\s]+)/.exec(props.className ?? '')?.[1];
  if (language?.toLowerCase() === 'mermaid') return <DiagramBlock code={code} />;
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
    'mentra-icon': ({ node }: RichProps) => <InlineIcon name={String(node?.properties.name ?? '')} />,
    'mentra-color': ({ node, children }: RichProps) => <ColorText tone={String(node?.properties.tone ?? '')} hex={node?.properties.hex ? String(node.properties.hex) : undefined}>{children}</ColorText>,
    'mentra-bar': ({ node }: RichProps) => <div className="my-4"><ProgressBar mode="meter" label={String(node?.properties.label ?? '')} value={Number(node?.properties.value)} max={Number(node?.properties.max)} unit={String(node?.properties.unit ?? '')} /></div>,
    'mentra-details': ({ node, children }: RichProps) => <details className="my-4 rounded-panel border border-border px-4 py-3"><summary className="ui-disclosure cursor-pointer font-medium text-heading">{String(node?.properties.title ?? 'Explanation')}</summary><div className="mt-2">{children}</div></details>,
    'mentra-callout': ({ node, children }: RichProps) => <aside className="rich-callout my-4 rounded-panel border border-border bg-surface p-4"><div className="font-medium"><ColorText tone={String(node?.properties.tone ?? 'info')}>{String(node?.properties.title ?? '')}</ColorText></div>{children}</aside>,
  }), [linkComponent]);
  const markdown = useMemo(() => normalizeMathDelimiters(content), [content]);
  const directives = usesRichDirectives(content);
  const diagrams = /(?:```|~~~)\s*mermaid/i.test(content);
  const remarkPlugins = useMemo(() => [remarkGfm, remarkMath, remarkMathCurrency, ...(directives ? [remarkDirective] : []), ...(directives || diagrams ? [remarkRichContent] : []), ...(plugins ?? noPlugins)], [directives, diagrams, plugins]);
  return <div className="markdown-content"><ReactMarkdown remarkPlugins={remarkPlugins}
    rehypePlugins={[[rehypeKatex, { trust: false, maxExpand: 500, maxSize: 20, throwOnError: false }]]} components={components}>{markdown}</ReactMarkdown></div>;
}
