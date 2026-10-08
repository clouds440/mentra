import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import mentraLogo from '../../assets/mentra-logo.png';
import type { ChatMessageData } from '../../types/chat';
import { useMemo, useState, type ReactNode } from 'react';
import { SourceViewer, sourceLocation } from '../library/SourceViewer';
import type { SourceReference } from '../../types/rag';

interface MarkdownNode { type: string; value?: string; url?: string; children?: MarkdownNode[] }
function citationPlugin(tokens: string[]) {
  return () => (tree: MarkdownNode) => {
    function visit(node: MarkdownNode) {
      if (['code', 'inlineCode', 'link'].includes(node.type) || !node.children) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value) { visit(child); return [child]; }
        const parts: MarkdownNode[] = []; let start = 0;
        for (const match of child.value.matchAll(/\[\[(S\d+)\]\]/g)) {
          if (!tokens.includes(match[1])) continue;
          const index = match.index ?? 0;
          parts.push({ type: 'text', value: child.value.slice(start, index) }, { type: 'link', url: `#mentra-source-${match[1]}`, children: [{ type: 'text', value: `[${match[1]}]` }] });
          start = index + match[0].length;
        }
        parts.push({ type: 'text', value: child.value.slice(start) }); return parts;
      });
    }
    visit(tree);
  };
}

interface ChatMessageProps {
  message: ChatMessageData;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const [source, setSource] = useState<SourceReference>();
  const isAssistant = message.role === 'assistant';
  const citations = useMemo(() => citationPlugin(message.citations ?? []), [message.citations]);
  // Keep the renderer identity stable so opening the dialog retains its trigger
  // node and native dialog focus restoration works for keyboard users.
  const markdownComponents = useMemo(() => ({ a: ({ href, children }: { href?: string; children?: ReactNode }) => {
    const token = href?.startsWith('#mentra-source-') ? href.slice('#mentra-source-'.length) : undefined;
    const found = message.sources?.find(s => s.token === token && message.citations?.includes(s.token));
    return found ? <button className="text-accent underline" onClick={() => setSource(found)} aria-label={`Open cited source ${found.title}`}>{children}</button> : <a href={href} rel="noopener noreferrer">{children}</a>;
  } }), [message.sources, message.citations]);

  return (
    <article
      aria-label={isAssistant ? 'Mentra response' : 'Your message'}
      className={isAssistant ? 'flex gap-3.5' : 'flex justify-end'}
    >
      {isAssistant && (
        <div
          aria-hidden="true"
          className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center"
        >
          <img alt="" className="h-6 w-6 object-contain" src={mentraLogo} />
        </div>
      )}
      <div
        className={
          isAssistant
            ? 'min-w-0 max-w-full flex-1 text-[14px] leading-7 text-body'
              : 'max-w-[88%] whitespace-pre-wrap rounded-2xl border border-border bg-message px-4 py-3 text-[14px] leading-6 text-foreground sm:max-w-[78%]'
        }
      >
        {isAssistant ? (
          <div className="markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm, citations]} components={markdownComponents}>{message.content}</ReactMarkdown>
            {message.sources && message.sources.length > 0 && <details className="mt-4 rounded-xl border border-border px-3 py-2 text-sm"><summary className="cursor-pointer text-muted">Study sources ({message.sources.length})</summary><ul className="mt-2 space-y-2">{message.sources.map(s => <li key={s.token}><button className="text-left text-accent hover:underline" onClick={() => setSource(s)}>{message.citations?.includes(s.token) ? `[${s.token}] Cited: ` : 'Consulted: '}{s.title} · {sourceLocation(s)}</button></li>)}</ul></details>}
            {message.retrieval_warning && <p className="mt-3 text-xs text-muted">{message.retrieval_warning}</p>}
            {message.retrieval_status && ['unavailable', 'no_matches', 'no_eligible_sources'].includes(message.retrieval_status) && <p className="mt-3 text-xs text-subtle">{message.retrieval_status === 'unavailable' ? 'Study material retrieval was unavailable for this answer.' : 'No supporting Library passages were found for this answer.'}</p>}
            {source && <SourceViewer source={source} includeArchived={source.include_archived ?? false} onClose={() => setSource(undefined)} />}
          </div>
        ) : (
          message.content
        )}
      </div>
    </article>
  );
}

interface ThinkingIndicatorProps {
  label?: string;
}

export function ThinkingIndicator({ label = '' }: ThinkingIndicatorProps) {
  return (
    <div aria-live="polite" className="flex items-center gap-3.5 text-sm text-subtle">
      <span className="grid h-7 w-7 place-items-center">
        <img alt="" aria-hidden="true" className="h-6 w-6 object-contain" src={mentraLogo} />
      </span>
      <span className="flex items-center gap-2">
        {label}
        <span aria-hidden="true" className="flex gap-1">
          <i className="h-1 w-1 animate-pulse rounded-full bg-subtle" />
          <i className="h-1 w-1 animate-pulse rounded-full bg-subtle [animation-delay:150ms]" />
          <i className="h-1 w-1 animate-pulse rounded-full bg-subtle [animation-delay:300ms]" />
        </span>
      </span>
    </div>
  );
}
