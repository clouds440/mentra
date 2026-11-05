import { BookOpen, Brain, FileText, History, ListTree, PanelRight } from 'lucide-react';
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { ChatMessageData } from '../../types/chat';
import type { StoredMessage } from '../../types/conversations';
import type { HistoryReference, MemoryReference } from '../../types/memories';
import type { SourceReference } from '../../types/rag';
import { getMessages } from '../../services/conversations';
import { SourceReader, sourceLocation } from '../library/SourceViewer';
import { Button, buttonStyles, Skeleton } from '../ui';
import { SourceLink } from '../webSearch/SourceLink';
import { safeSource } from '../webSearch/WebCitation';
import { WebCitations } from '../webSearch/WebCitations';
import { useSidePanelActions } from '../workspace/sidePanelState';
import { ChatAttachmentPreview } from './ChatAttachmentPreview';

const ReferenceContent = lazy(() => import('./HistoryReferenceViewer').then(module => ({ default: module.HistoryReferenceContent })));
const referenceTitle = (item: HistoryReference | MemoryReference) => 'title' in item ? item.title : 'Saved memory';
type SourceGroup = 'web' | 'study' | 'personal';
const groups = [
  { kind: 'web', title: 'Web sources', Icon: ListTree },
  { kind: 'study', title: 'Study sources', Icon: BookOpen },
  { kind: 'personal', title: 'Personal context', Icon: History },
] as const;

function count(message: ChatMessageData, group: SourceGroup) {
  if (group === 'web') return message.web_sources?.length ?? 0;
  if (group === 'study') return message.sources?.length ?? 0;
  return (message.history_references?.length ?? 0) + (message.memory_references?.length ?? 0);
}
export const hasChatSources = (message: ChatMessageData) => !!message.attachments?.length || groups.some(group => count(message, group.kind) > 0);

export function useSourceTabs() {
  const panel = useSidePanelActions();
  const openSource = useCallback((source: SourceReference) => {
    panel?.open({ title: source.title, icon: <BookOpen size={14} aria-hidden="true" />,
      content: <SourceReader source={source} includeArchived={source.include_archived ?? false} /> });
  }, [panel]);
  const openReference = useCallback((reference: HistoryReference | MemoryReference) => {
    const Icon = 'memory_id' in reference ? Brain : History;
    panel?.open({ title: referenceTitle(reference), icon: <Icon size={14} aria-hidden="true" />,
      content: <Suspense fallback={<Skeleton variant="text" className="p-4" />}><ReferenceContent reference={reference} onClose={panel.hide} /></Suspense> });
  }, [panel]);
  return { openSource, openReference };
}

function SourceList({ title, children }: { title: string; children: ReactNode }) {
  return <div className="p-4"><h2 className="font-semibold text-heading">{title}</h2><ul className="mt-2 divide-y divide-border">{children}</ul></div>;
}

export function ChatSourceCollection({ message, group }: { message: ChatMessageData; group?: SourceGroup }) {
  const { openSource, openReference } = useSourceTabs();
  const references = [...(message.history_references ?? []), ...(message.memory_references ?? [])];
  return <>
    {(!group || group === 'web') && <WebCitations sources={message.web_sources} citations={message.web_citations} searches={message.web_searches} />}
    {(!group || group === 'study') && !!message.sources?.length && <SourceList title="Study sources">{message.sources.map(source => <li key={source.token}>
      <button type="button" className="workspace-source-row" onClick={() => openSource(source)}>{message.citations?.includes(source.token) ? '[' + source.token + '] Cited: ' : 'Consulted: '}{source.title} · {sourceLocation(source)}</button>
    </li>)}</SourceList>}
    {(!group || group === 'personal') && !!references.length && <SourceList title="Personal context consulted">{references.map(item => <li key={item.token}>
      <button type="button" className="workspace-source-row" onClick={() => openReference(item)}>[{item.token}] {referenceTitle(item)}</button>
    </li>)}</SourceList>}
  </>;
}

export function ChatSourceButtons({ message }: { message: ChatMessageData }) {
  const panel = useSidePanelActions();
  if (!panel || !hasChatSources(message)) return null;
  return <div className="mt-4 flex flex-wrap gap-2">{groups.map(({ kind, title, Icon }) => {
    const total = count(message, kind);
    return total > 0 && <button key={kind} type="button" className={buttonStyles({ size: 'sm', variant: 'secondary' })} title="Open in side panel"
      onClick={() => panel.open({ title, icon: <Icon size={14} aria-hidden="true" />, content: <ChatSourceCollection message={message} group={kind} /> })}>
      <PanelRight size={15} aria-hidden="true" />{title} ({total})
    </button>;
  })}</div>;
}

function unique<T>(items: T[], identify: (item: T) => string) {
  const seen = new Set<string>();
  return items.filter(item => {
    const key = identify(item);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
}

/** Both the panel launcher and its dropdown can browse the whole conversation
 * without loading old messages into the chat viewport. */
export function ChatSourceCatalog({ messages, conversationId, before, compact = false }: {
  messages: ChatMessageData[]; conversationId?: string; before: number | null; compact?: boolean;
}) {
  const panel = useSidePanelActions();
  const { openSource, openReference } = useSourceTabs();
  const [earlier, setEarlier] = useState<StoredMessage[]>([]);
  const [next, setNext] = useState<number | null>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const request = useRef<AbortController>();
  useEffect(() => () => request.current?.abort(), []);
  const cursor = next === undefined ? before : next;
  async function loadEarlier() {
    if (!cursor || !conversationId || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError('');
    try {
      const page = await getMessages(conversationId, cursor, controller.signal);
      if (controller.signal.aborted) return;
      setEarlier(items => [...page.items, ...items]);
      const previous = page.items[0]?.sequence;
      setNext(page.has_more && previous && previous < cursor ? previous : null);
    } catch {
      if (!controller.signal.aborted) setError('Couldn’t load earlier sources. Try again.');
    } finally {
      if (request.current === controller) request.current = undefined;
      if (!controller.signal.aborted) setLoading(false);
    }
  }
  const { web, study, personal, files } = useMemo(() => {
    const newest = [...earlier, ...messages].reverse();
    return {
      web: unique(newest.flatMap(message => message.web_sources ?? []).filter(safeSource), item => item.url),
      study: unique(newest.flatMap(message => message.sources ?? []), item => [item.document_id, item.version_id, item.generation_id, item.chunk_id].join(':')),
      personal: unique(newest.flatMap(message => [...(message.history_references ?? []), ...(message.memory_references ?? [])]), item =>
        'memory_id' in item ? item.memory_id + ':' + item.revision : item.conversation_id + ':' + item.sequence),
      files: unique(newest.flatMap(message => message.conversation_id ? (message.attachments ?? []).map(file => ({ file, conversation: message.conversation_id! })) : []), item => item.file.id),
    };
  }, [messages, earlier]);
  return <>
    {!!web.length && <SourceList title="Web sources">{web.map(item => <li key={item.url}>
      <SourceLink href={item.url} sourceTitle={item.title} className="workspace-source-row block">
        <span className="block">{item.title}</span><span className="text-xs text-muted">{item.domain}</span>
        {!compact && item.excerpt && <span className="mt-1 line-clamp-2 break-words text-xs leading-5 text-muted">{item.excerpt}</span>}
      </SourceLink>
    </li>)}</SourceList>}
    {!!study.length && <SourceList title="Study sources">{study.map(item => <li key={[item.document_id, item.version_id, item.generation_id, item.chunk_id].join(':')}>
      <button type="button" className="workspace-source-row" onClick={() => openSource(item)}>{item.title} · {sourceLocation(item)}</button>
    </li>)}</SourceList>}
    {!!personal.length && <SourceList title="Personal context">{personal.map(item => {
      const key = 'memory_id' in item ? item.memory_id + ':' + item.revision : item.conversation_id + ':' + item.sequence;
      return <li key={key}><button type="button" className="workspace-source-row" onClick={() => openReference(item)}>{referenceTitle(item)}</button></li>;
    })}</SourceList>}
    {!!files.length && <SourceList title="Attachments">{files.map(({ file, conversation }) => <li key={file.id}>
      <button type="button" className="workspace-source-row" onClick={() => panel?.open({ title: file.filename,
        reuseKey: 'attachment:' + conversation + ':' + file.id, icon: <FileText size={14} aria-hidden="true" />,
        content: <ChatAttachmentPreview filename={file.filename} fileId={file.id} conversationId={conversation} /> })}>{file.filename}</button>
    </li>)}</SourceList>}
    {!web.length && !study.length && !personal.length && !files.length && <p className="p-4 text-sm text-muted">No sources in the loaded messages.</p>}
    {cursor && conversationId && <div className="px-4 pb-4">
      {error && <p role="alert" className="mb-2 text-xs text-danger">{error}</p>}
      <Button size="sm" variant="secondary" loading={loading} disabled={loading} onClick={() => void loadEarlier()}>Load earlier sources</Button>
    </div>}
  </>;
}
