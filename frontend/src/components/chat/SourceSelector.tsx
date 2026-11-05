import { BookOpenText, X } from 'lucide-react';
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { Button, Input, buttonStyles } from '../ui';
import { getMaterial, libraryPage, materialError } from '../../services/rag';
import type { ChatSelection, MaterialDocument } from '../../types/rag';
import { Popover } from '../ui/Popover';
import { Skeleton } from '../ui/Skeleton';

type PickerKey = KeyboardEvent<HTMLTextAreaElement | HTMLInputElement>;
export interface SourcePickerHandle {
  handleKeyDown: (event: PickerKey) => boolean;
  selectionIssue: () => string | undefined;
}
const maxReferences = 20;

export const SourceSelector = forwardRef<SourcePickerHandle, {
  selection: ChatSelection; onChange: (value: ChatSelection) => void; disabled: boolean;
  picker: 'mention' | 'browse' | null; anchor: RefObject<HTMLElement>; onClose: (restoreFocus?: boolean) => void; onPick: () => void;
  query: string; onQueryChange: (value: string) => void; onActiveOptionChange: (id: string | undefined) => void;
}>(function SourceSelector({ selection, onChange, disabled, picker, anchor, onClose, onPick, query, onQueryChange, onActiveOptionChange }, ref) {
  const open = !!picker && !disabled;
  const ids = selection.document_ids ?? [];
  const selectedKey = JSON.stringify(ids);
  const [known, setKnown] = useState<Record<string, MaterialDocument | null>>({});
  const [documents, setDocuments] = useState<MaterialDocument[]>([]);
  const [active, setActive] = useState(0);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [settledQuery, setSettledQuery] = useState<string>();
  const [error, setError] = useState('');
  const request = useRef<AbortController>();
  const results = useRef<HTMLDivElement>(null);
  const normalized = query.trim().slice(0, 200);
  const pendingQuery = settledQuery !== normalized;
  const matches = pendingQuery ? [] : documents;
  const includeArchived = !!selection.include_archived;

  useEffect(() => {
    const controller = new AbortController();
    const missing = ids.filter(id => !(id in known));
    if (missing.length) void Promise.all(missing.map(async id => {
      try { return [id, await getMaterial(id, controller.signal)] as const; }
      catch { return [id, null] as const; }
    })).then(rows => {
      if (!controller.signal.aborted) setKnown(previous => ({ ...previous, ...Object.fromEntries(rows) }));
    });
    return () => controller.abort();
  }, [selectedKey]);

  async function load(controller: AbortController, start: number, search: string) {
    setBusy(true); setError('');
    try {
      const page = await libraryPage(start, false, controller.signal, undefined, search);
      if (controller.signal.aborted) return;
      const contexts = new Set(page.contexts.filter(context => context.status !== 'ARCHIVED').map(context => context.context_id));
      const ready = page.items.filter(item => item.active_generation_id && !item.archived && item.context_ids.some(id => contexts.has(id)));
      setDocuments(previous => start ? [...previous, ...ready.filter(item => !previous.some(knownItem => knownItem.id === item.id))] : ready);
      setOffset(page.offset + page.items.length); setTotal(page.total);
    } catch (reason) { if (!controller.signal.aborted) setError(materialError(reason)); }
    finally {
      if (!controller.signal.aborted) { setBusy(false); setSettledQuery(search); }
    }
  }

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    request.current = controller;
    setActive(0); setSettledQuery(undefined); setDocuments([]); setOffset(0); setTotal(0); setError('');
    const timer = setTimeout(() => void load(controller, 0, normalized), normalized ? 200 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [open, normalized]);

  const activeId = open && matches[active] ? 'study-material-option-' + active : undefined;
  useEffect(() => { onActiveOptionChange(activeId); }, [activeId, onActiveOptionChange]);
  useEffect(() => {
    const option = activeId && document.getElementById(activeId);
    const list = results.current;
    if (!option || !list) return;
    const row = option.getBoundingClientRect(), bounds = list.getBoundingClientRect();
    if (row.top < bounds.top) list.scrollTop += row.top - bounds.top;
    else if (row.bottom > bounds.bottom) list.scrollTop += row.bottom - bounds.bottom;
  }, [activeId]);

  function pick(item: MaterialDocument) {
    if (disabled || (!ids.includes(item.id) && ids.length >= maxReferences)) return;
    setKnown(previous => ({ ...previous, [item.id]: item }));
    if (!ids.includes(item.id)) onChange({ mode: 'SOURCE_SPECIFIC', document_ids: [...ids, item.id],
      ...(includeArchived ? { include_archived: true } : {}) });
    onPick();
  }

  function ready(id: string) {
    return !!known[id]?.active_generation_id && (includeArchived || !known[id]?.archived);
  }
  function selectionIssue() {
    if (ids.some(id => !(id in known))) return 'Wait for the referenced material to load before sending.';
    if (ids.some(id => !ready(id))) return 'Remove or reselect unavailable material before sending.';
  }
  function handleKeyDown(event: PickerKey) {
    if (!open || event.nativeEvent.isComposing) return false;
    if (event.key === 'Escape') { event.preventDefault(); onClose(true); return true; }
    if (event.key === 'Tab' && picker === 'mention') { onClose(); return false; }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (matches[active]) pick(matches[active]);
      return true;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setActive(previous => matches.length ? (previous + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length : 0);
      return true;
    }
    return false;
  }
  useImperativeHandle(ref, () => ({ handleKeyDown, selectionIssue }));

  return <>
    {!!ids.length && <ul aria-label="Referenced materials" className="flex max-h-24 flex-wrap gap-1.5 overflow-y-auto px-2.5 pb-1 pt-1">
      {ids.map(id => {
        const title = known[id]?.title ?? (id in known ? 'Unavailable material' : 'Loading material…');
        const unavailable = id in known && !ready(id);
        return <li key={id} className="inline-flex max-w-full items-center gap-1.5 rounded-control bg-accent/10 pl-2 text-xs font-medium text-accent">
          <BookOpenText size={13} className="shrink-0" aria-hidden="true" />
          <span className="min-w-0 truncate" title={title}>{title}{unavailable && known[id] ? ' (unavailable)' : ''}</span>
          <button type="button" disabled={disabled} aria-label={'Remove reference to ' + title}
            className="grid size-8 shrink-0 place-items-center rounded-control hover:bg-accent/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
            onClick={() => { const rest = ids.filter(item => item !== id); onChange(rest.length ? { ...selection, document_ids: rest } : { mode: 'STANDARD' }); }}>
            <X size={14} aria-hidden="true" />
          </button>
        </li>;
      })}
    </ul>}
    <Popover anchor={anchor} open={open} onClose={() => onClose()} placement="above" matchWidth role="dialog" label="Choose study material" focusOnOpen={picker === 'browse'}>
      <div className="space-y-2 p-2">
        <p className="text-sm font-medium text-heading">Reference study material</p>
        {picker === 'browse' && <Input type="search" aria-label="Search study material" placeholder="Search titles or filenames…" maxLength={200}
          value={query} onChange={event => onQueryChange(event.target.value)} onKeyDown={handleKeyDown}
          aria-controls="study-material-results" aria-activedescendant={activeId} />}
        <div ref={results} id="study-material-results" role="listbox" aria-label="Study material" className="max-h-40 overflow-y-auto">
          {matches.map((item, index) => <button key={item.id} id={'study-material-option-' + index} type="button"
            role="option" aria-selected={index === active} disabled={!ids.includes(item.id) && ids.length >= maxReferences} onClick={() => pick(item)}
            className={'block w-full rounded-lg px-3 py-2 text-left text-sm text-heading disabled:opacity-50 ' + (index === active ? 'bg-hover' : 'hover:bg-hover')}>
            <span className="block truncate">{item.title}{ids.includes(item.id) ? ' · Referenced' : ''}</span>
            <span className="block truncate text-xs text-subtle">{item.filename}</span>
          </button>)}
        </div>
        {ids.length >= maxReferences && <p role="status" className="text-xs text-muted">You can reference up to 20 materials.</p>}
        {(busy || pendingQuery) && <Skeleton variant="list" rows={2} />}
        {!busy && !pendingQuery && !matches.length && !error && <p role="status" className="text-xs text-muted">{normalized ? 'No matching ready material.' : 'No ready material on this page.'}</p>}
        {error && <p role="alert" className="text-xs text-danger">{error}</p>}
        {(error || offset < total) && <Button size="sm" variant="secondary" disabled={busy || pendingQuery} onClick={() => {
          if (request.current) void load(request.current, offset, normalized);
        }}>{error ? 'Retry' : 'Load more material'}</Button>}
        <Link to="/library" className={buttonStyles({ variant: 'ghost', size: 'sm' })}>Manage Library</Link>
      </div>
    </Popover>
  </>;
});
