import { MarkdownContent } from '../content/MarkdownContent';
import mentraLogo from '../../assets/mentra-logo.png';
import type { ChatMessageData } from '../../types/chat';
import { useMemo, useState, lazy, Suspense, type ReactNode } from 'react';
import { SourceViewer, sourceLocation } from '../library/SourceViewer';
import type { SourceReference } from '../../types/rag';
import type { HistoryReference, MemoryReference } from '../../types/memories';
import { Spinner } from '../ui/Spinner';
import { ChatAttachmentCard } from './ChatAttachmentCard';
import { EventProposalCard } from '../events/EventProposalCard';
import { Link } from 'react-router-dom';

const HistoryReferenceViewer = lazy(() => import('./HistoryReferenceViewer').then(module => ({ default: module.HistoryReferenceViewer })));
const ChatAssessmentCard = lazy(() => import('../assessments/ChatAssessmentCard').then(module => ({ default: module.ChatAssessmentCard })));

interface MarkdownNode { type: string; value?: string; url?: string; children?: MarkdownNode[] }
function citationPlugin(tokens: string[]) {
  return () => (tree: MarkdownNode) => {
    function visit(node: MarkdownNode) {
      if (['code', 'inlineCode', 'link'].includes(node.type) || !node.children) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value) { visit(child); return [child]; }
        const parts: MarkdownNode[] = []; let start = 0;
        for (const match of child.value.matchAll(/\[\[([SHM]\d+)\]\]/g)) {
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
  const [historyReference, setHistoryReference] = useState<HistoryReference | MemoryReference>();
  const isAssistant = message.role === 'assistant';
  const citations = useMemo(() => citationPlugin([...(message.citations ?? []), ...(message.history_references ?? []).map(item => item.token), ...(message.memory_references ?? []).map(item => item.token)]), [message.citations, message.history_references, message.memory_references]);
  // Keep the renderer identity stable so opening the dialog retains its trigger
  // node and native dialog focus restoration works for keyboard users.
  const markdownComponents = useMemo(() => ({ a: ({ href, children }: { href?: string; children?: ReactNode }) => {
    const token = href?.startsWith('#mentra-source-') ? href.slice('#mentra-source-'.length) : undefined;
    const found = message.sources?.find(s => s.token === token && message.citations?.includes(s.token));
    const history = [...(message.history_references ?? []), ...(message.memory_references ?? [])].find(item => item.token === token);
    if (history) return <button className="text-accent underline" onClick={() => setHistoryReference(history)} aria-label={`Open ${history.token.startsWith('H') ? 'history' : 'memory'} reference ${history.token}`}>{children}</button>;
    return found ? <button className="text-accent underline" onClick={() => setSource(found)} aria-label={`Open cited source ${found.title}`}>{children}</button> : <a href={href} rel="noopener noreferrer">{children}</a>;
  } }), [message.sources, message.citations, message.history_references, message.memory_references]);

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
              : 'min-w-0 max-w-[94%] rounded-2xl border border-border bg-message px-4 py-3 text-[14px] leading-6 text-foreground sm:max-w-[88%]'
        }
      >
        {isAssistant ? (
          <div className="markdown-content">
            <MarkdownContent content={message.content} plugins={[citations]} linkComponent={markdownComponents.a} />
            {message.event_proposals?.map(proposal => <EventProposalCard key={proposal.id} initial={proposal} />)}
            {!!message.assessment_cards?.length && <Suspense fallback={<span role="status"><Spinner />Loading assessment…</span>}>{message.assessment_cards.map(card => <ChatAssessmentCard key={card.attempt_id ?? card.id ?? card.assessment_id} initial={card} />)}</Suspense>}
            {!!message.event_references?.length && <div className="mt-3 flex flex-wrap gap-3">{message.event_references.map(event => <Link key={event.id} className="text-sm text-accent underline" to={`/progress?tab=events&event=${event.id}`}>{event.title}</Link>)}</div>}
            {message.sources && message.sources.length > 0 && <details className="mt-4 rounded-xl border border-border px-3 py-2 text-sm"><summary className="cursor-pointer text-muted">Study sources ({message.sources.length})</summary><ul className="mt-2 space-y-2">{message.sources.map(s => <li key={s.token}><button className="text-left text-accent hover:underline" onClick={() => setSource(s)}>{message.citations?.includes(s.token) ? `[${s.token}] Cited: ` : 'Consulted: '}{s.title} · {sourceLocation(s)}</button></li>)}</ul></details>}
            {message.retrieval_warning && <p className="mt-3 text-xs text-muted">{message.retrieval_warning}</p>}
            {message.retrieval_status && ['unavailable', 'no_matches', 'no_eligible_sources'].includes(message.retrieval_status) && <p className="mt-3 text-xs text-subtle">{message.retrieval_status === 'unavailable' ? 'Study material retrieval was unavailable for this answer.' : 'No supporting Library passages were found for this answer.'}</p>}
            {source && <SourceViewer source={source} includeArchived={source.include_archived ?? false} onClose={() => setSource(undefined)} />}
            {historyReference && <Suspense fallback={<span role="status"><Spinner />Loading reference…</span>}><HistoryReferenceViewer reference={historyReference} onClose={() => setHistoryReference(undefined)} /></Suspense>}
            {((message.history_references?.length ?? 0) + (message.memory_references?.length ?? 0)) > 0 && <details className="mt-4 rounded-xl border border-border px-3 py-2 text-sm"><summary className="cursor-pointer text-muted">Personal context consulted</summary><ul className="mt-2 space-y-2">{[...(message.history_references ?? []), ...(message.memory_references ?? [])].map(item => <li key={item.token}><button className="text-accent hover:underline" onClick={() => setHistoryReference(item)}>[{item.token}] {'title' in item ? item.title : 'Saved memory'}</button></li>)}</ul></details>}
          </div>
        ) : (
          <><MarkdownContent content={message.content} />
          {message.conversation_id && message.attachments?.map(file => <ChatAttachmentCard key={file.id} file={file} conversationId={message.conversation_id!} />)}</>
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
    <div role="status" aria-live="polite" className="flex items-center gap-3.5 text-sm text-subtle">
      <span className="grid h-7 w-7 place-items-center">
        <img alt="" aria-hidden="true" className="h-6 w-6 object-contain" src={mentraLogo} />
      </span>
      <span className="flex items-center gap-2">
        {label}
        <span aria-hidden="true" className="flex gap-1">
          <i className="h-1 w-1 motion-safe:animate-pulse rounded-full bg-subtle" />
          <i className="h-1 w-1 motion-safe:animate-pulse rounded-full bg-subtle [animation-delay:150ms]" />
          <i className="h-1 w-1 motion-safe:animate-pulse rounded-full bg-subtle [animation-delay:300ms]" />
        </span>
      </span>
    </div>
  );
}
