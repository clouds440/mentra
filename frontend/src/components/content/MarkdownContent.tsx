import { Children, isValidElement, useMemo, type ReactNode } from 'react';
import ReactMarkdown, { type Components, type Options } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CodeBlock } from './CodeBlock';

function MarkdownCode({ children }: { children?: ReactNode }) {
  const child = Children.toArray(children).find(isValidElement);
  if (!child) return <pre>{children}</pre>;
  const props = child.props as { children?: ReactNode; className?: string };
  const code = Children.toArray(props.children).join('').replace(/\n$/, '');
  const language = /language-([^\s]+)/.exec(props.className ?? '')?.[1];
  return <CodeBlock code={code} language={language} />;
}
export function MarkdownContent({ content, linkComponent, plugins = [] }: { content: string; linkComponent?: Components['a']; plugins?: Options['remarkPlugins'] }) {
  const components = useMemo<Components>(() => ({
    pre: MarkdownCode,
    a: linkComponent ?? (({ children, href }) => <a href={href} rel="noopener noreferrer">{children}</a>),
    table: ({ children }) => <div className="markdown-table-scroll"><table>{children}</table></div>,
  }), [linkComponent]);
  return <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm, ...(plugins ?? [])]} components={components}>{content}</ReactMarkdown></div>;
}
