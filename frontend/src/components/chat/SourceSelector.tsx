import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Select } from '../ui';
import { getMaterial, listMaterials, listContexts, materialError } from '../../services/rag';
import type { MaterialDocument, LearningContext, ChatSelection } from '../../types/rag';
import { ApiError } from '../../services/api';

export function SourceSelector({ selection, onChange, disabled }: { selection: ChatSelection; onChange: (value: ChatSelection) => void; disabled: boolean }) {
  const [documents, setDocuments] = useState<MaterialDocument[]>([]); const [contexts, setContexts] = useState<LearningContext[]>([]); const [error, setError] = useState('');
  const [nextOffset, setNextOffset] = useState(0); const [total, setTotal] = useState(0); const [loadingMore, setLoadingMore] = useState(false);
  const controllerRef = useRef<AbortController>();
  const [notice, setNotice] = useState('');
  function choose(value: ChatSelection) { setNotice(''); onChange(value); }
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    async function load() {
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
    }
    void load(); window.addEventListener('focus', load); return () => { controller.abort(); window.removeEventListener('focus', load); };
  }, [selection.include_archived, selection.document_ids?.join(','), selection.context_ids?.join(',')]);
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
  return <details className="mb-3 rounded-xl border border-border px-3 py-2 text-sm"><summary className="cursor-pointer text-muted">{selection.mode === 'SOURCE_SPECIFIC' ? 'Using selected material' : selection.mode === 'CROSS_CONTEXT' ? 'Using selected learning contexts' : 'Use relevant study material automatically'}</summary>
    <div className="mt-3 space-y-3"><label className="block">Study sources<Select aria-label="Study sources" className="mt-1" value={selection.mode} disabled={disabled} onChange={e => choose({ mode: e.target.value as ChatSelection['mode'], include_archived: e.target.value === 'STANDARD' ? false : selection.include_archived })}><option value="STANDARD">Automatic relevant material</option><option value="SOURCE_SPECIFIC">Choose material</option><option value="CROSS_CONTEXT">Choose learning contexts</option></Select></label>
    {selection.mode === 'SOURCE_SPECIFIC' && <label className="block">Selected material<Select multiple className="mt-1" value={selection.document_ids ?? []} disabled={disabled} onChange={e => choose({ ...selection, document_ids: Array.from(e.target.selectedOptions, o => o.value) })}>{documents.filter(d => d.active_generation_id && (selection.include_archived || (!d.archived && contexts.some(c => c.status !== 'ARCHIVED' && d.context_ids.includes(c.context_id))))).map(d => <option key={d.id} value={d.id}>{d.title}{d.archived ? ' (archived)' : ''}</option>)}</Select></label>}
    {selection.mode === 'SOURCE_SPECIFIC' && nextOffset < total && <Button size="sm" variant="secondary" disabled={disabled || loadingMore} onClick={() => void loadMore()}>{loadingMore ? 'Loading material…' : 'Load more material'}</Button>}
    {selection.mode === 'CROSS_CONTEXT' && <label className="block">Selected learning contexts<Select multiple className="mt-1" value={selection.context_ids ?? []} disabled={disabled} onChange={e => choose({ ...selection, context_ids: Array.from(e.target.selectedOptions, o => o.value) })}>{contexts.filter(c => c.status !== 'ARCHIVED' || selection.include_archived).map(c => <option key={c.context_id} value={c.context_id}>{c.name} ({c.status.toLowerCase()})</option>)}</Select></label>}
    {selection.mode !== 'STANDARD' && <label className="flex gap-2"><input type="checkbox" disabled={disabled} checked={selection.include_archived ?? false} onChange={e => choose({ ...selection, include_archived: e.target.checked })} />Allow explicitly selected archived material</label>}
    {notice && <p role="status" className="text-muted">{notice}</p>}
    {error && <p role="alert" className="text-danger">{error}</p>}<Link to="/library" className="inline-block text-accent">Add or manage material in Library</Link>
    <p className="text-xs text-subtle">Only ready material can ground an answer. Selected sources stay within your Library.</p></div>
  </details>;
}
