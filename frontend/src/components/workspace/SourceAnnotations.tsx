import { Globe, Quote, X } from 'lucide-react';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router';
import { resourceKey, type PanelResource, type SourceAnnotation } from '../../types/sourceAnnotations';
import { buttonStyles, IconButton } from '../ui';
import { SourceLink } from '../webSearch/SourceLink';
import { useSidePanelActions } from './sidePanelState';

const LIMIT = 4;
const MAX_LENGTH = 1600;
const empty: SourceAnnotation[] = [];
const Drafts = createContext<Record<string, SourceAnnotation[]>>({});
const Update = createContext<React.Dispatch<React.SetStateAction<Record<string, SourceAnnotation[]>>>>(() => {});
const keyOf = (annotation: SourceAnnotation) => {
  const { source } = annotation;
  return JSON.stringify([source.kind === 'chat' ? source.title : resourceKey(source), annotation.mode === 'page' ? null : annotation.text]);
};

export function AnnotationDraftProvider({ children }: { children: ReactNode }) {
  const [drafts, update] = useState<Record<string, SourceAnnotation[]>>({});
  return <Update.Provider value={update}><Drafts.Provider value={drafts}>{children}</Drafts.Provider></Update.Provider>;
}

export function useResetNewChatExcerpts() {
  const update = useContext(Update);
  return () => update(current => {
    if (!current['/']) return current;
    const remaining = { ...current };
    delete remaining['/'];
    return remaining;
  });
}

export function useAnnotationDraft() {
  const { pathname } = useLocation();
  const annotations = useContext(Drafts)[pathname] ?? empty;
  const update = useContext(Update);
  function removeItems(items: SourceAnnotation[]) {
    const removed = new Set(items.map(keyOf));
    update(current => {
      const next = (current[pathname] ?? empty).filter(item => !removed.has(keyOf(item)));
      if (next.length) return { ...current, [pathname]: next };
      const remaining = { ...current };
      delete remaining[pathname];
      return remaining;
    });
  }
  return { annotations, remove: (index: number) => removeItems([annotations[index]]),
    clear: () => { if (annotations.length) removeItems(annotations); },
    restore: (path: string) => {
      if (!annotations.length) return;
      update(current => {
        const keys = new Set(annotations.map(keyOf));
        const remaining = (current[path] ?? empty).filter(item => !keys.has(keyOf(item)));
        return { ...current, [path]: [...annotations, ...remaining].slice(0, LIMIT) };
      });
    } };
}

export function useStageSource() {
  const panel = useSidePanelActions();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const target = pathname === '/' || pathname.startsWith('/chat/') ? pathname : '/';
  const existing = useContext(Drafts)[target] ?? empty;
  const update = useContext(Update);
  function unavailable(annotation: SourceAnnotation) {
    if (existing.some(item => keyOf(item) === keyOf(annotation))) return 'Already added to chat';
    if (existing.length >= LIMIT) return 'Up to 4 references per message';
  }
  function stage(annotation: SourceAnnotation, origin: HTMLElement | null) {
    if (unavailable(annotation)) return false;
    update(current => {
      const items = current[target] ?? empty;
      return items.length >= LIMIT || items.some(item => keyOf(item) === keyOf(annotation))
        ? current : { ...current, [target]: [...items, annotation] };
    });
    if (origin?.closest('.workspace-side-panel[aria-modal="true"]')) panel?.hide();
    if (target !== pathname) void navigate(target);
    return true;
  }
  return { stage, unavailable };
}

export function SourceAnnotationChips({ annotations, remove, disabled }: {
  annotations?: SourceAnnotation[]; remove?: (index: number) => void; disabled?: boolean;
}) {
  if (!annotations?.length) return null;
  const containsPage = annotations.some(item => item.mode === 'page');
  return <ul aria-label={remove ? containsPage ? 'Draft references' : 'Draft excerpts' : containsPage ? 'Referenced sources' : 'Referenced excerpts'} className={'source-annotation-list' + (remove ? ' px-2.5 pb-1 pt-2' : '')}>
    {annotations.map((annotation, index) => <li key={keyOf(annotation)} className="source-annotation-chip">
      <details className="min-w-0" data-no-excerpt>
        <summary className="flex min-w-0 cursor-pointer items-center gap-1.5">
          {annotation.mode === 'page' ? <Globe size={13} className="shrink-0" aria-hidden="true" /> : <Quote size={13} className="shrink-0" aria-hidden="true" />}
          <span className="truncate">{annotation.mode === 'page' ? annotation.source.title : annotation.text}</span>
          <span className="sr-only"> · {annotation.mode === 'page' ? 'Web page' : annotation.source.title}</span>
        </summary>
        {annotation.mode !== 'page' && <blockquote dir="auto" className="mt-1 whitespace-pre-wrap break-words text-foreground">{annotation.text}</blockquote>}
        <cite className="text-xs not-italic text-muted">{annotation.source.kind === 'web'
          ? <SourceLink href={annotation.source.url} className="underline underline-offset-2">{annotation.source.title}</SourceLink>
          : annotation.source.title}</cite>
      </details>
      {remove && <IconButton size="sm" className="h-6 min-h-6 w-6 shrink-0 p-0" disabled={disabled}
        aria-label={(annotation.mode === 'page' ? 'Remove page ' : 'Remove excerpt ') + (index + 1)} onClick={() => remove(index)}><X size={12} aria-hidden="true" /></IconButton>}
    </li>)}
  </ul>;
}

type Selected = { annotation: Extract<SourceAnnotation, { text: string }>; x: number; y: number };
const element = (node: Node) => node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;

export function SourceSelection({ scope, source, onStage }: { scope: RefObject<HTMLElement | null>; source?: PanelResource; onStage?: () => void }) {
  const [selected, setSelected] = useState<Selected>();
  const { stage, unavailable } = useStageSource();
  const frame = useRef(0);
  const read = useCallback(() => {
    const selection = window.getSelection();
    const root = scope.current;
    if (!selection || selection.isCollapsed || !selection.rangeCount || !root || root.closest('[hidden], [aria-hidden="true"]')) return setSelected(undefined);
    const range = selection.getRangeAt(0);
    const start = element(range.startContainer);
    const end = element(range.endContainer);
    if (!start || !end || !root.contains(start) || !root.contains(end) ||
        start.closest('button, input, textarea, select, [data-no-excerpt]') ||
        end.closest('button, input, textarea, select, [data-no-excerpt]')) return setSelected(undefined);
    const fromChat = start.closest<HTMLElement>('[data-chat-excerpt]');
    const role = fromChat?.dataset.chatExcerpt;
    const webExcerpt = start.closest<HTMLElement>('[data-web-excerpt]');
    const web = webExcerpt && webExcerpt === end.closest('[data-web-excerpt]') ? webExcerpt.dataset : undefined;
    const redirect = start.closest<HTMLElement>('[data-reader-url]');
    const readerUrl = redirect === end.closest('[data-reader-url]') ? redirect?.dataset.readerUrl : undefined;
    let provenance: SourceAnnotation['source'] | undefined = source;
    if (source?.kind === 'web' && readerUrl) provenance = { ...source, url: readerUrl };
    else if (web?.webExcerpt && web.sourceTitle) provenance = { kind: 'web', title: web.sourceTitle, url: web.webExcerpt };
    else if (fromChat === end.closest('[data-chat-excerpt]') && (role === 'Mentra response' || role === 'Your message')) {
      provenance = { kind: 'chat', title: role };
    }
    if (provenance && provenance.kind !== 'chat') provenance = { ...provenance, title: [...provenance.title].slice(0, 300).join('') };
    const text = selection.toString().trim();
    if (!provenance || !text) return setSelected(undefined);
    const rect = range.getBoundingClientRect();
    const bounds = root.getBoundingClientRect();
    if (!rect.height || rect.bottom < bounds.top || rect.top > bounds.bottom) return setSelected(undefined);
    setSelected({ annotation: { source: provenance, text }, x: Math.min(window.innerWidth - 82, Math.max(82, (rect.left + rect.right) / 2)),
      y: Math.max(8, Math.min(window.innerHeight - 40, Math.max(bounds.top, rect.top) - 36)) });
  }, [scope, source]);
  useEffect(() => {
    function queue() { cancelAnimationFrame(frame.current); frame.current = requestAnimationFrame(read); }
    document.addEventListener('selectionchange', queue);
    const reposition = () => { if (!window.getSelection()?.isCollapsed) queue(); };
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      cancelAnimationFrame(frame.current);
      document.removeEventListener('selectionchange', queue);
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
    };
  }, [read]);
  if (!selected) return null;
  const { annotation, x, y } = selected;
  const error = [...annotation.text].length > MAX_LENGTH ? 'Select a shorter excerpt' : unavailable(annotation);
  return createPortal(<div className="source-selection" data-no-excerpt style={{ left: x, top: y }}>
    {error ? <span role="status">{error}</span> :
      <button type="button" className={buttonStyles({ size: 'sm', variant: 'secondary' })} onPointerDown={event => event.preventDefault()}
        onClick={() => {
          if (!stage(annotation, scope.current)) return;
          window.getSelection()?.removeAllRanges();
          setSelected(undefined);
          onStage?.();
        }}><Quote size={13} aria-hidden="true" /> Send to chat</button>}
  </div>, scope.current?.closest('dialog[open], [aria-modal="true"]') ?? document.body);
}
