import { Children, isValidElement, memo, useMemo, type ReactNode } from 'react';
import ReactMarkdown, { type Components, type Options } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { normalizeMathDelimiters, remarkMathCurrency } from '../../lib/mathMarkdown';
import { CodeBlock } from './CodeBlock';

function MarkdownCode({ children }: { children?: ReactNode }) {
  const child = Children.toArray(children).find(isValidElement);
  if (!child) return <pre>{children}</pre>;
  const props = child.props as { children?: ReactNode; className?: string };
  const code = Children.toArray(props.children).join('').replace(/\n$/, '');
  const language = /language-([^\s]+)/.exec(props.className ?? '')?.[1];
  return <CodeBlock code={code} language={language} />;
}
export const MarkdownContent = memo(function MarkdownContent({ content, linkComponent, plugins = [] }: { content: string; linkComponent?: Components['a']; plugins?: Options['remarkPlugins'] }) {
  const components = useMemo<Components>(() => ({
    pre: MarkdownCode,
    a: linkComponent ?? (({ children, href }) => <a href={href} rel="noopener noreferrer">{children}</a>),
    table: ({ children }) => <div className="markdown-table-scroll"><table>{children}</table></div>,
  }), [linkComponent]);
  const markdown = useMemo(() => normalizeMathDelimiters(content), [content]);
  return <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm, remarkMath, remarkMathCurrency, ...(plugins ?? [])]}
    rehypePlugins={[[rehypeKatex, { trust: false, maxExpand: 500, maxSize: 20, throwOnError: false }]]} components={components}>{markdown}</ReactMarkdown></div>;
});
