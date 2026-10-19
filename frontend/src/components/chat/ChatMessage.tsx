import { buttonStyles } from '../ui/Button';
import { Skeleton } from '../ui/Skeleton';
import { MarkdownContent } from '../content/MarkdownContent';
import { MentraLogo } from '../brand/MentraLogo';
import type { ChatMessageData } from '../../types/chat';
import { memo, useMemo, useState, lazy, Suspense, type ReactNode } from 'react';
import { SourceViewer, sourceLocation } from '../library/SourceViewer';
import type { SourceReference } from '../../types/rag';
import type { HistoryReference, MemoryReference } from '../../types/memories';
import { ChatAttachmentCard } from './ChatAttachmentCard';
import { EventProposalCard } from '../events/EventProposalCard';
import { ChoiceCard } from './ChoiceCard';
import { Link } from 'react-router-dom';
import { WebCitation } from '../webSearch/WebCitation';
import { WebCitations } from '../webSearch/WebCitations';
import { CopyResponse } from './CopyResponse';

const HistoryReferenceViewer = lazy(() => import('./HistoryReferenceViewer').then(module => ({ default: module.HistoryReferenceViewer })));
const ChatAssessmentCard = lazy(() => import('../assessments/ChatAssessmentCard').then(module => ({ default: module.ChatAssessmentCard })));
const AssessmentGenerationCard = lazy(() => import('../assessments/AssessmentGenerationCard').then(module => ({ default: module.AssessmentGenerationCard })));

interface MarkdownNode { type: string; value?: string; url?: string; children?: MarkdownNode[]; position?: { start: { offset?: number }; end: { offset?: number } } }
function citationPlugin(tokens: string[], content: string) {
  return () => (tree: MarkdownNode) => {
    function visit(node: MarkdownNode) {
      if (['code', 'inlineCode', 'link'].includes(node.type) || !node.children) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value) { visit(child); return [child]; }
        const parts: MarkdownNode[] = []; let start = 0;
        const raw = content.slice(child.position?.start.offset ?? 0, child.position?.end.offset ?? 0);
        const originals = [...raw.matchAll(/\[\[([SHMW]\d+)\]\]/g)];
        let occurrence = 0;
        for (const match of child.value.matchAll(/\[\[([SHMW]\d+)\]\]/g)) {
          const original = originals[occurrence++];
          const before = original ? raw.slice(0, original.index) : '';
          const slashCount = /\\+$/.exec(before)?.[0].length ?? 0;
          if (!original || slashCount % 2 === 1) continue;
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
  reveal?: boolean;
}

export const ChatMessage = memo(function ChatMessage({ message, reveal = false }: ChatMessageProps) {
  const [source, setSource] = useState<SourceReference>();
  const [historyReference, setHistoryReference] = useState<HistoryReference | MemoryReference>();
  const isAssistant = message.role === 'assistant';
  const citations = useMemo(() => citationPlugin([...(message.citations ?? []), ...(message.web_citations ?? []), ...(message.history_references ?? []).map(item => item.token), ...(message.memory_references ?? []).map(item => item.token)], message.content), [message.content, message.citations, message.web_citations, message.history_references, message.memory_references]);
  const markdownPlugins = useMemo(() => [citations], [citations]);
  // Keep the renderer identity stable so opening the dialog retains its trigger
  // node and native dialog focus restoration works for keyboard users.
  const markdownComponents = useMemo(() => ({ a: ({ href, children }: { href?: string; children?: ReactNode }) => {
    const token = href?.startsWith('#mentra-source-') ? href.slice('#mentra-source-'.length) : undefined;
    const found = message.sources?.find(s => s.token === token && message.citations?.includes(s.token));
    const history = [...(message.history_references ?? []), ...(message.memory_references ?? [])].find(item => item.token === token);
    const web = message.web_sources?.find(item => item.token === token && message.web_citations?.includes(item.token));
    if (web) return <WebCitation source={web}>{children}</WebCitation>;
    if (history) return <button className="text-accent underline" onClick={() => setHistoryReference(history)} aria-label={`Open ${history.token.startsWith('H') ? 'history' : 'memory'} reference ${history.token}`}>{children}</button>;
    return found ? <button className="text-accent underline" onClick={() => setSource(found)} aria-label={`Open cited source ${found.title}`}>{children}</button> : <a href={href} rel="noopener noreferrer">{children}</a>;
  } }), [message.sources, message.citations, message.web_sources, message.web_citations, message.history_references, message.memory_references]);

  return (
    <article
      data-message-id={message.id}
      aria-label={isAssistant ? 'Mentra response' : 'Your message'}
      className={isAssistant ? `flex flex-col gap-2 sm:flex-row sm:gap-3.5${reveal ? ' chat-response-reveal' : ''}` : 'flex justify-end'}
    >
      {isAssistant && (
        <div
          aria-hidden="true"
          className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center"
        >
          <MentraLogo className="h-6 w-6" />
        </div>
      )}
      <div
        className={
          isAssistant
            ? 'min-w-0 max-w-full flex-1 text-[14px] leading-7 text-body'
              : 'flex min-w-0 max-w-[94%] flex-col items-end gap-2 text-[14px] leading-6 text-foreground sm:max-w-[88%]'
        }
      >
        {isAssistant ? (
          <div className="markdown-content">
            <MarkdownContent content={message.content} plugins={markdownPlugins} linkComponent={markdownComponents.a} />
            <WebCitations sources={message.web_sources} citations={message.web_citations} searches={message.web_searches} />
            {message.conversation_id && message.interactions?.map(card => <ChoiceCard key={card.id} card={card} messageId={message.id} conversationId={message.conversation_id!} />)}
            {message.event_proposals?.map(proposal => <EventProposalCard key={proposal.id} initial={proposal} />)}
            {!!message.assessment_cards?.length && <Suspense fallback={<Skeleton variant="card" />}>{message.assessment_cards.map(card => 'generation_job_id' in card ? <AssessmentGenerationCard key={card.id} id={card.generation_job_id} title={card.title} /> : <ChatAssessmentCard key={card.attempt_id ?? card.id ?? card.assessment_id} initial={card} />)}</Suspense>}
            {!!message.event_references?.length && <div className="mt-3 flex flex-wrap gap-3">{message.event_references.map(event => <Link key={event.id} className={buttonStyles({ variant: 'secondary', size: 'sm', className: 'max-w-full text-left' })} to={`/progress?tab=events&event=${event.id}`}>{event.title}</Link>)}</div>}
            {message.sources && message.sources.length > 0 && <details className="mt-4 rounded-xl border border-border px-3 py-2 text-sm"><summary className="ui-disclosure cursor-pointer text-muted">Study sources ({message.sources.length})</summary><ul className="mt-2 space-y-2">{message.sources.map(s => <li key={s.token}><button className="block w-full rounded-control px-2 py-2 text-left text-accent transition-colors duration-150 hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setSource(s)}>{message.citations?.includes(s.token) ? `[${s.token}] Cited: ` : 'Consulted: '}{s.title} · {sourceLocation(s)}</button></li>)}</ul></details>}
            {source && <SourceViewer source={source} includeArchived={source.include_archived ?? false} onClose={() => setSource(undefined)} />}
            {historyReference && <Suspense fallback={<Skeleton variant="text" />}><HistoryReferenceViewer reference={historyReference} onClose={() => setHistoryReference(undefined)} /></Suspense>}
            {((message.history_references?.length ?? 0) + (message.memory_references?.length ?? 0)) > 0 && <details className="mt-4 rounded-xl border border-border px-3 py-2 text-sm"><summary className="ui-disclosure cursor-pointer text-muted">Personal context consulted</summary><ul className="mt-2 space-y-2">{[...(message.history_references ?? []), ...(message.memory_references ?? [])].map(item => <li key={item.token}><button className="block w-full rounded-control px-2 py-2 text-left text-accent transition-colors duration-150 hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" onClick={() => setHistoryReference(item)}>[{item.token}] {'title' in item ? item.title : 'Saved memory'}</button></li>)}</ul></details>}
            {!!message.content.trim() && <CopyResponse content={message.content} />}
          </div>
        ) : (
          <>{message.conversation_id && !!message.attachments?.length && <div className="flex max-w-full flex-wrap justify-end gap-3">{message.attachments.map(file => <ChatAttachmentCard key={file.id} file={file} conversationId={message.conversation_id!} />)}</div>}
          {!!message.content.trim() && <><div className="max-w-full rounded-2xl border border-border bg-message px-4 py-3"><MarkdownContent content={message.content} /></div><CopyResponse content={message.content} subject="message" /></>}</>
        )}
      </div>
    </article>
  );
});

interface ThinkingIndicatorProps {
  label?: string;
}

export function ThinkingIndicator({ label = '' }: ThinkingIndicatorProps) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3.5 text-sm text-subtle">
      <span className="grid h-7 w-7 place-items-center">
        <MentraLogo working className="h-6 w-6" />
      </span>
      <span className="flex items-center gap-2">
        <span className="activity-label">{label}</span>
        <span aria-hidden="true" className="flex gap-1">
          <i className="h-1 w-1 motion-safe:animate-pulse rounded-full bg-subtle" />
          <i className="h-1 w-1 motion-safe:animate-pulse rounded-full bg-subtle [animation-delay:150ms]" />
          <i className="h-1 w-1 motion-safe:animate-pulse rounded-full bg-subtle [animation-delay:300ms]" />
        </span>
      </span>
    </div>
  );
}
