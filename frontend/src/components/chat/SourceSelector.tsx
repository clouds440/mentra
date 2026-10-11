import { Skeleton } from '../ui/Skeleton';
import { Toggle } from '../ui/Toggle';
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { Button, Select } from '../ui';
import { getMaterial, listMaterials, listContexts, materialError } from '../../services/rag';
import type { MaterialDocument, LearningContext, ChatSelection } from '../../types/rag';
import { Popover } from '../ui/Popover';
import { ApiError } from '../../services/api';

export interface SourcePickerHandle { handleKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => boolean }

export const SourceSelector = forwardRef<SourcePickerHandle, {
  selection: ChatSelection; onChange: (value: ChatSelection) => void; disabled: boolean;
  pickerOpen: boolean; anchor: RefObject<HTMLElement>; onClose: () => void; onPick: () => void;
  query: string; onActiveOptionChange: (id: string | undefined) => void;
}>(function SourceSelector({ selection, onChange, disabled, pickerOpen, anchor, onClose, onPick, query, onActiveOptionChange }, ref) {
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => { if (pickerOpen) setActive(0); }, [pickerOpen]);
  const [documents, setDocuments] = useState<MaterialDocument[]>([]); const [contexts, setContexts] = useState<LearningContext[]>([]); const [error, setError] = useState('');
  const [nextOffset, setNextOffset] = useState(0); const [total, setTotal] = useState(0); const [loadingMore, setLoadingMore] = useState(false);
  const controllerRef = useRef<AbortController>();
  const [notice, setNotice] = useState('');
  function choose(value: ChatSelection) { setNotice(''); onChange(value); }
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoadingMore(false);
    async function load() {
      setLoading(true);
      try {
        const [list, ctx] = await Promise.all([listMaterials(0, selection.include_archived ? undefined : false, controller.signal), listContexts(controller.signal)]);
        const items = [...list.items];
        for (const id of selection.document_ids ?? []) if (!items.some(d => d.id === id)) {
          try { items.push(await getMaterial(id, controller.signal)); }
          catch (e) { if (!(e instanceof ApiError && e.status === 404)) throw e; }
        }
        if (!controller.signal.aborted) {
          setDocuments(items); setContexts(ctx); setNextOffset(list.items.length); setTotal(list.total); setError('');
          const documentIds = selection.document_ids?.filter(id => items.some(d => d.id === id && d.active_generation_id &&
            (selection.include_archived || (!d.archived && ctx.some(c => c.status !== 'ARCHIVED' && d.context_ids.includes(c.context_id))))));
          const contextIds = selection.context_ids?.filter(id => ctx.some(c => c.context_id === id && (selection.include_archived || c.status !== 'ARCHIVED')));
          if (documentIds?.length !== selection.document_ids?.length || contextIds?.length !== selection.context_ids?.length) {
            setNotice('Some selected material is unavailable or archived. Choose available sources before sending.');
            onChange({ ...selection, document_ids: documentIds, context_ids: contextIds });
          }
        }
      } catch (e) { if (!controller.signal.aborted) setError(materialError(e)); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load(); window.addEventListener('focus', load); return () => { controller.abort(); window.removeEventListener('focus', load); };
  }, [selection.include_archived, selection.document_ids?.join(','), selection.context_ids?.join(','), pickerOpen]);
  async function loadMore() {
    const controller = controllerRef.current;
    setLoadingMore(true);
    try {
      const list = await listMaterials(nextOffset, selection.include_archived ? undefined : false, controller?.signal);
      if (!controller?.signal.aborted) {
        setDocuments(previous => [...previous, ...list.items.filter(item => !previous.some(old => old.id === item.id))]);
        setNextOffset(list.offset + list.items.length); setTotal(list.total); setError('');
      }
    } catch (e) { if (!controller?.signal.aborted) setError(materialError(e)); }
    finally { if (!controller?.signal.aborted) setLoadingMore(false); }
  }
  const available = documents.filter(d => d.active_generation_id && (selection.include_archived ||
    (!d.archived && contexts.some(c => c.status !== 'ARCHIVED' && d.context_ids.includes(c.context_id)))));
  const matches = available.filter(d => `${d.title} ${d.filename}`.toLocaleLowerCase().includes(query.toLocaleLowerCase().trim()));
  // The Library API is paginated; include later pages when searching.
  useEffect(() => {
    if (pickerOpen && query.trim() && !loading && !loadingMore && !error && nextOffset < total) void loadMore();
  }, [pickerOpen, query, loading, loadingMore, error, nextOffset, total]);
  useEffect(() => { setActive(0); }, [query, matches.length]);
  useEffect(() => {
    if (pickerOpen) document.getElementById(`study-material-option-${active}`)?.scrollIntoView({ block: 'nearest' });
  }, [active, pickerOpen]);
  function pick(document: MaterialDocument) {
    choose({ mode: 'SOURCE_SPECIFIC', include_archived: selection.include_archived,
      document_ids: [...new Set([...(selection.mode === 'SOURCE_SPECIFIC' ? selection.document_ids ?? [] : []), document.id])] });
    onPick();
  }
  useEffect(() => {
    onActiveOptionChange(pickerOpen && matches[active] ? `study-material-option-${active}` : undefined);
  }, [pickerOpen, active, matches[active]?.id, onActiveOptionChange]);
  useImperativeHandle(ref, () => ({ handleKeyDown(event) {
    if (!pickerOpen || disabled || event.nativeEvent.isComposing) return false;
    if (event.key === 'Escape') { event.preventDefault(); onClose(); return true; }
    if (event.key === 'Tab') { onClose(); return false; }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault(); if (matches[active]) pick(matches[active]); return true;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setActive(previous => matches.length ? (previous + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length : 0);
      return true;
    }
    return false;
  } }));
  return <>
    <Popover anchor={anchor} open={pickerOpen && !disabled} onClose={onClose} placement="above" matchWidth role="dialog" label="Choose study material">
      <div className="p-2">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-heading">Discuss study material</p>
          <span className="text-[10px] text-subtle">↑ ↓ to browse · Enter to select</span>
        </div>
        <p className="text-xs text-subtle">{query ? `Results for “${query}”` : 'Type after @ in your message to search.'}</p>
        <div id="study-material-results" role="listbox" aria-label="Study material" className="mt-2 max-h-40 overflow-y-auto">
          {matches.map((document, index) => <button key={document.id} id={`study-material-option-${index}`} type="button"
            role="option" aria-selected={index === active} onClick={() => pick(document)}
            className={`block w-full rounded-lg px-3 py-2 text-left text-sm text-heading ${index === active ? 'bg-hover' : 'hover:bg-hover'}`}>
            <span className="block truncate">{document.title}{document.archived ? ' (archived)' : ''}</span>
            <span className="block truncate text-xs text-subtle">{document.filename}</span>
          </button>)}
        </div>
        {(loading || loadingMore) && <Skeleton variant="list" />}
        {!loading && !loadingMore && !matches.length && !error && <p role="status" className="mt-2 text-xs text-muted">{query ? 'No matching ready material.' : 'No ready material yet. Add material in Library.'}</p>}
        {error && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
        {nextOffset < total && <Button size="sm" variant="secondary" disabled={loading || loadingMore} loading={loadingMore} onClick={() => void loadMore()}>Load more material</Button>}
        <div className="mt-2 flex flex-wrap gap-3 border-t border-border pt-2 text-xs">
          <button type="button" className="text-accent" onClick={() => { choose({ mode: 'CROSS_CONTEXT', include_archived: selection.include_archived }); onPick(); }}>Choose learning contexts</button>
          <Link to="/library" className="text-accent">Manage Library</Link>
        </div>
      </div>
    </Popover>
    {selection.mode !== 'STANDARD' && <details className="mb-3 rounded-xl border border-border px-3 py-2 text-sm"><summary className="cursor-pointer text-muted">{selection.mode === 'SOURCE_SPECIFIC' ? 'Using selected material' : selection.mode === 'CROSS_CONTEXT' ? 'Using selected learning contexts' : 'Use relevant study material automatically'}</summary>
    <div className="mt-3 space-y-3"><label className="block">Study sources<Select aria-label="Study sources" className="mt-1" value={selection.mode} disabled={disabled} onChange={e => choose({ mode: e.target.value as ChatSelection['mode'], include_archived: e.target.value === 'STANDARD' ? false : selection.include_archived })}><option value="STANDARD">Automatic relevant material</option><option value="SOURCE_SPECIFIC">Choose material</option><option value="CROSS_CONTEXT">Choose learning contexts</option></Select></label>
    {selection.mode === 'SOURCE_SPECIFIC' && <label className="block">Selected material<Select multiple className="mt-1" value={selection.document_ids ?? []} disabled={disabled} onChange={e => choose({ ...selection, document_ids: Array.from(e.target.selectedOptions, o => o.value) })}>{documents.filter(d => d.active_generation_id && (selection.include_archived || (!d.archived && contexts.some(c => c.status !== 'ARCHIVED' && d.context_ids.includes(c.context_id))))).map(d => <option key={d.id} value={d.id}>{d.title}{d.archived ? ' (archived)' : ''}</option>)}</Select></label>}
    {selection.mode === 'SOURCE_SPECIFIC' && nextOffset < total && <Button size="sm" variant="secondary" disabled={disabled || loadingMore} loading={loadingMore} onClick={() => void loadMore()}>{'Load more material'}</Button>}
    {selection.mode === 'CROSS_CONTEXT' && <label className="block">Selected learning contexts<Select multiple className="mt-1" value={selection.context_ids ?? []} disabled={disabled} onChange={e => choose({ ...selection, context_ids: Array.from(e.target.selectedOptions, o => o.value) })}>{contexts.filter(c => c.status !== 'ARCHIVED' || selection.include_archived).map(c => <option key={c.context_id} value={c.context_id}>{c.name} ({c.status.toLowerCase()})</option>)}</Select></label>}
    <Toggle label="Allow explicitly selected archived material" disabled={disabled} checked={selection.include_archived ?? false} onChange={e => choose({ ...selection, include_archived: e.target.checked })} />
    {notice && <p role="status" className="text-muted">{notice}</p>}
    {error && <p role="alert" className="text-danger">{error}</p>}<Link to="/library" className="inline-block text-accent">Add or manage material in Library</Link>
    <p className="text-xs text-subtle">Only ready material can ground an answer. Selected sources stay within your Library.</p></div>
  </details>}
  </>;
});
