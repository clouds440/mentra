import { BookOpen, Brain, FileText, Globe, History, Pin, PinOff } from 'lucide-react';
import { createContext, lazy, Suspense, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, apiRequest } from '../../services/api';
import { resourceKey, type PanelResource, type PinnedSource } from '../../types/sourceAnnotations';
import { IconButton } from '../ui/IconButton';
import { Skeleton } from '../ui';
import { useSidePanelActions } from './sidePanelState';

const ReopenedSource = lazy(() => import('./ReopenedSource'));
const path = '/api/v1/workspace/pins';
const icons = { web: Globe, library: BookOpen, attachment: FileText, history: History, memory: Brain };
const Pins = createContext<{ items: PinnedSource[]; error: string; busy: boolean;
  change: (source: PanelResource, pin?: PinnedSource) => Promise<void> }>({ items: [], error: '', busy: false, change: async () => {} });

export function PinnedSourcesProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<PinnedSource[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const request = useRef<AbortController>(undefined);
  useEffect(() => {
    const controller = new AbortController();
    request.current = controller;
    void apiRequest<PinnedSource[]>(path, { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted && Array.isArray(result)) setItems(result);
    }).catch(() => { if (!controller.signal.aborted) setError('Could not load pinned sources.'); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, []);
  async function change(source: PanelResource, pin?: PinnedSource) {
    const signal = request.current?.signal;
    if (!signal || signal.aborted || busy) return;
    setBusy(true);
    setError('');
    try {
      if (pin) {
        await apiRequest<void>(path + '/' + encodeURIComponent(pin.id), { method: 'DELETE', signal });
        if (!signal.aborted) setItems(current => current.filter(item => item.id !== pin.id));
      } else {
        const saved = await apiRequest<PinnedSource>(path, { method: 'POST', body: JSON.stringify(source), signal });
        if (!signal.aborted) setItems(current => [saved, ...current.filter(item => item.id !== saved.id)]);
      }
    } catch (reason) {
      if (!signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Could not update pinned sources. Try again.');
    } finally { if (!signal.aborted) setBusy(false); }
  }
  return <Pins.Provider value={{ items, busy, error, change }}>{children}</Pins.Provider>;
}

export const usePinnedSources = () => useContext(Pins);

export function PinSourceButton({ source }: { source: PanelResource }) {
  const { items, change, busy } = usePinnedSources();
  const pin = items.find(item => resourceKey(item.source) === resourceKey(source));
  const label = pin ? 'Unpin source' : 'Pin source';
  const Icon = pin ? PinOff : Pin;
  return <IconButton size="sm" aria-label={label} title={label} disabled={busy} onClick={() => void change(source, pin)}>
    <Icon size={15} aria-hidden="true" />
  </IconButton>;
}

export function PinnedSourceList({ onChoose }: { onChoose?: () => void }) {
  const { items, change, busy, error } = usePinnedSources();
  const panel = useSidePanelActions();
  return <div className="px-3 py-2">
    {error && <p role="alert" className="p-2 text-xs text-danger">{error}</p>}
    {!items.length && <p className="p-2 text-sm text-muted">{busy ? 'Loading pins…' : 'Pin a source to keep it here across chats.'}</p>}
    {!!items.length && <ul className="divide-y divide-border">{items.map(item => {
      const source = item.source;
      const Icon = icons[source.kind];
      return <li key={item.id} className="flex items-center gap-1">
        <button type="button" className="workspace-source-row flex min-w-0 flex-1 items-center gap-2" onClick={() => {
          panel?.open({ title: source.title, resource: source, reuseKey: 'pin:' + item.id, icon: <Icon size={14} aria-hidden="true" />,
            content: <Suspense fallback={<Skeleton variant="text" className="p-4" />}><ReopenedSource source={source} /></Suspense> });
          onChoose?.();
        }}><Icon className="shrink-0" size={14} aria-hidden="true" /><span className="truncate">{source.title}</span></button>
        <IconButton size="sm" disabled={busy} aria-label={'Unpin ' + source.title} onClick={() => void change(source, item)}><PinOff size={14} aria-hidden="true" /></IconButton>
      </li>;
    })}</ul>}
  </div>;
}
