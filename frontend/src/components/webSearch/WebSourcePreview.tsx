import { BookOpen, EllipsisVertical, ExternalLink, Globe, MessageSquarePlus, Pin, PinOff } from 'lucide-react';
import { useContext, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { apiRequest } from '../../services/api';
import type { PanelResource, SourceAnnotation } from '../../types/sourceAnnotations';
import { buttonStyles, IconButton } from '../ui';
import { ActionMenu } from '../ui/ActionMenu';
import { usePinSource } from '../workspace/PinnedSources';
import { useStageSource } from '../workspace/SourceAnnotations';
import { PanelEntryScope } from '../workspace/sidePanelState';
import { previewUrl, SourceLink } from './SourceLink';

interface PreviewResult { status: 'available' | 'blocked' | 'unavailable'; url?: string }

interface ReaderResult { url: string; blocks: string[]; links: { url: string; title: string }[] }

const readerHistory = new WeakMap<object, { reading: boolean; reader?: ReaderResult | null }>();

export function WebSourcePreview({ source, navigation }: { source: Extract<PanelResource, { kind: 'web' }>; navigation: ReactNode }) {
  const { url: href, title } = source;
  const url = new URL(href);
  const anchor = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const [menuOpen, setMenuOpen] = useState(false);
  const { pinned, busy, toggle } = usePinSource(source);
  const { stage, unavailable } = useStageSource();
  const annotation: SourceAnnotation = { mode: 'page', source };
  const addUnavailable = unavailable(annotation);
  const entry = useContext(PanelEntryScope);
  const previous = entry && readerHistory.get(entry);
  const [reading, setReading] = useState(previous?.reading ?? false);
  const [reader, setReader] = useState<ReaderResult | null | undefined>(previous?.reader);
  useEffect(() => {
    if (entry) readerHistory.set(entry, { reading, reader });
  }, [entry, reading, reader]);
  useEffect(() => {
    if (!reading || reader !== undefined) return;
    const controller = new AbortController();
    void apiRequest<ReaderResult | null>('/api/v1/web/reader', {
      method: 'POST', body: JSON.stringify({ url: href }), signal: controller.signal,
    }).then(value => { if (!controller.signal.aborted) setReader(value); })
      .catch(() => { if (!controller.signal.aborted) setReader(null); });
    return () => controller.abort();
  }, [href, reading, reader]);
  const [result, setResult] = useState<PreviewResult>();
  useEffect(() => {
    if (reading || result !== undefined) return;
    const controller = new AbortController();
    const requestUrl = new URL(href);
    requestUrl.hash = '';
    const timer = setTimeout(() => {
      setResult({ status: 'unavailable' });
      controller.abort();
    }, 6000);
    void apiRequest<PreviewResult>('/api/v1/web/preview', {
      method: 'POST', body: JSON.stringify({ url: requestUrl.href }), signal: controller.signal,
    }).then(value => {
      if (!controller.signal.aborted) setResult(value);
    }).catch(() => {
      if (!controller.signal.aborted) setResult({ status: 'unavailable' });
    }).finally(() => clearTimeout(timer));
    return () => { clearTimeout(timer); controller.abort(); };
  }, [href, reading, result]);
  const frame = result?.status === 'available' && result.url ? previewUrl(result.url) : undefined;
  if (frame && !frame.hash) frame.hash = url.hash;
  return <div className="workspace-web-preview">
    <header className="workspace-resource-toolbar workspace-web-toolbar" data-no-excerpt>
      {navigation}
      <span className="min-w-0 flex-1 truncate px-1 text-xs text-muted" dir="ltr" title={url.hostname}>{url.hostname}</span>
      <IconButton ref={anchor} className="workspace-web-menu-trigger" aria-label="Website actions" title="Website actions"
        aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuOpen ? menuId : undefined} onClick={() => setMenuOpen(open => !open)}>
        <EllipsisVertical size={17} aria-hidden="true" />
      </IconButton>
      <ActionMenu anchor={anchor} open={menuOpen} onClose={() => setMenuOpen(false)} id={menuId} label="Website actions" align="end" items={[
        { id: 'add', label: addUnavailable ?? 'Add to chat', icon: MessageSquarePlus, disabled: !!addUnavailable,
          onSelect: () => { stage(annotation, anchor.current); } },
        { id: 'reader', label: reading ? 'Exit Reader' : 'Reader', icon: BookOpen, onSelect: () => setReading(value => !value) },
        { id: 'browser', label: 'Open in browser', icon: ExternalLink, href: url.href },
        { id: 'pin', label: pinned ? 'Unpin source' : 'Pin source', icon: pinned ? PinOff : Pin, disabled: busy, onSelect: toggle },
      ]} />
    </header>
    {reading ? reader ? <div data-reader-url={reader.url} className="space-y-3 p-4 text-sm leading-relaxed">
      {reader.blocks.map((block, index) => <p key={index} dir="auto" className="break-words">{block}</p>)}
      {!!reader.links.length && <ul className="space-y-2 border-t border-border pt-3">{reader.links.map(link => <li key={link.url}>
        <SourceLink href={link.url} sourceTitle={link.title} className="text-accent hover:underline">{link.title}</SourceLink>
      </li>)}</ul>}
    </div> : <div className="workspace-web-status" role="status">{reader === null ? <>Readable text is unavailable for this page.
      <button type="button" className={buttonStyles({ size: 'sm', variant: 'ghost' })} onClick={() => setReader(undefined)}>Retry Reader</button></> : 'Loading readable text…'}</div>
    : frame ? <iframe src={frame.href} title={title} sandbox="allow-scripts" referrerPolicy="no-referrer"
      allow="camera 'none'; microphone 'none'; geolocation 'none'; payment 'none'; clipboard-read 'none'; clipboard-write 'none'"
      {...{ credentialless: '' }} /> : <div className="workspace-web-status" role="status">
      <Globe size={24} strokeWidth={1.5} aria-hidden="true" />
      <p className="text-sm font-medium text-heading">{!result ? 'Checking preview…' : result.status === 'blocked' ? 'This publisher restricts embedded previews' : 'Preview unavailable'}</p>
      {result && <p className="text-xs text-muted">Try Reader for selectable text, or open the original page in your browser.</p>}
    </div>}
  </div>;
}
