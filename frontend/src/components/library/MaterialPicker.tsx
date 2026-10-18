import { useEffect, useRef, useState } from 'react';
import { Button, Input, Select } from '../ui';
import { getMaterial, listMaterials, materialError } from '../../services/rag';
import type { MaterialDocument, MaterialList } from '../../types/rag';
import { X } from 'lucide-react';

export const materialSelectionKey = (ids: string[], contextId = '') => JSON.stringify([contextId, ids]);

export function MaterialPicker({ value, onChange, contextId, disabled = false, onValidityChange }: {
  value: string[]; onChange: (ids: string[]) => void; contextId?: string; disabled?: boolean;
  onValidityChange?: (state: { key: string; ready: boolean }) => void;
}) {
  const [search, setSearch] = useState(''), [query, setQuery] = useState('');
  const [page, setPage] = useState<MaterialList>();
  const [known, setKnown] = useState<Record<string, MaterialDocument>>({});
  const [error, setError] = useState(''), [loading, setLoading] = useState(false), [retry, setRetry] = useState(0);
  const [selectionError, setSelectionError] = useState('');
  const request = useRef<AbortController>();
  const selectedIds = useRef(value); selectedIds.current = value;
  const nextOffset = useRef(0);
  const hydratedRetry = useRef(0);
  useEffect(() => { const timer = setTimeout(() => setQuery(search.trim()), 250); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    const controller = new AbortController(); request.current = controller;
    setPage(undefined); setLoading(true); setError('');
    void listMaterials(0, false, controller.signal, contextId || undefined, query).then(result => {
      if (!controller.signal.aborted) { nextOffset.current = result.offset + result.items.length; setPage(result); setKnown(old => ({ ...Object.fromEntries(selectedIds.current.flatMap(id => old[id] ? [[id,old[id]]] : [])), ...Object.fromEntries(result.items.map(item => [item.id, item])) })); }
    }).catch(reason => { if (!controller.signal.aborted) setError(materialError(reason)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [contextId, query, retry]);
  const selectedKey = value.join(',');
  useEffect(() => {
    const controller = new AbortController();
    const ids = value.filter(id => !known[id] || hydratedRetry.current !== retry);
    hydratedRetry.current = retry;
    setSelectionError('');
    if (!ids.length) return () => controller.abort();
    // List results already carry owned readiness metadata. Hydrate only missing
    // preselected IDs, at most four requests at once, rather than N+1 on every pick.
    const results: PromiseSettledResult<MaterialDocument>[] = [];
    const failed: string[] = [];
    let next = 0;
    async function hydrate() {
      while (next < ids.length && !controller.signal.aborted) {
        const id = ids[next++];
        try { results.push({status:'fulfilled', value:await getMaterial(id, controller.signal)}); }
        catch (reason) { failed.push(id); results.push({status:'rejected', reason}); }
      }
    }
    void Promise.all(Array.from({length:Math.min(4,ids.length)}, hydrate)).then(() => {
      if (controller.signal.aborted) return;
      const items = results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []);
      setKnown(old => ({ ...Object.fromEntries(Object.entries(old).filter(([id]) => !failed.includes(id))), ...Object.fromEntries(items.map(item => [item.id, item])) }));
      if (results.some(result => result.status === 'rejected')) setSelectionError('Some selected materials are unavailable. Remove them or retry.');
    }).catch(reason => { if (!controller.signal.aborted) setSelectionError(materialError(reason)); });
    return () => controller.abort();
  }, [selectedKey, retry]);
  const eligible = (item: MaterialDocument | undefined) => !!item?.active_generation_id && !item.archived && (!contextId || item.context_ids.includes(contextId));
  useEffect(() => { onValidityChange?.({key:materialSelectionKey(value, contextId), ready:value.length>0 && value.length<=20 && value.every(id => eligible(known[id]))}); }, [selectedKey, contextId, known, onValidityChange]);
  async function more() {
    const controller = request.current;
    if (!page || loading || !controller || controller.signal.aborted) return;
    setLoading(true); setError('');
    try {
      const result = await listMaterials(nextOffset.current, false, controller.signal, contextId || undefined, query);
      if (!controller.signal.aborted) {
        nextOffset.current = result.offset + result.items.length;
        const items = [...page.items, ...result.items.filter(item => !page.items.some(previous => previous.id === item.id))].slice(-100);
        setPage({ ...result, offset:0, items });
        setKnown(old => ({ ...Object.fromEntries(selectedIds.current.flatMap(id => old[id] ? [[id,old[id]]] : [])), ...Object.fromEntries(items.map(item => [item.id,item])) }));
      }
    } catch (reason) { if (!controller?.signal.aborted) setError(materialError(reason)); }
    finally { if (!controller?.signal.aborted) setLoading(false); }
  }
  const options = [...new Set([...(page?.items.map(item => item.id) ?? []), ...value])].flatMap(id => known[id] ? [known[id]] : []);
  return <div className="space-y-2">
    <Input type="search" aria-label="Search assessment materials" placeholder="Search material titles or filenames…" maxLength={200} value={search} disabled={disabled} onChange={event => setSearch(event.target.value)} />
    <Select multiple aria-label="Assessment study documents" value={value} disabled={disabled} onChange={event => onChange(Array.from(event.target.selectedOptions, option => option.value))}>
      {options.filter(item => eligible(item) || value.includes(item.id)).map(item => <option key={item.id} value={item.id} disabled={!value.includes(item.id) && value.length>=20}>{item.title}{!eligible(item) ? ' (unavailable in this context)' : ''}</option>)}
      {value.filter(id => !known[id]).map(id => <option key={id} value={id}>Selected material (unavailable or loading)</option>)}
    </Select>
    <p className="text-xs text-muted">{value.length} selected · Choose up to 20 ready materials. Selections stay when you search or change pages.</p>
    {!!value.length && <ul className="grid gap-2 sm:grid-cols-2" aria-label="Selected assessment materials">{value.map(id => <li key={id} className="flex min-w-0 items-center gap-2 rounded-control border border-border bg-surface px-3 py-1.5"><span className="min-w-0 flex-1 break-words text-xs text-heading">{known[id]?.title ?? 'Selected material'}{!eligible(known[id]) && <span className="mt-0.5 block text-[10px] text-muted">Unavailable or still loading</span>}</span><Button size="sm" variant="ghost" className="shrink-0 px-2" disabled={disabled} aria-label={`Remove ${known[id]?.title ?? 'selected material'}`} onClick={() => onChange(value.filter(item => item!==id))}><X size={14} aria-hidden="true" /></Button></li>)}</ul>}
    {!!value.length && <Button size="sm" variant="ghost" disabled={disabled} onClick={() => onChange([])}>Clear selected materials</Button>}
    {loading && <p role="status" className="text-xs text-muted">Loading materials…</p>}
    {page && !page.items.length && !loading && <p className="text-xs text-muted">No matching materials.</p>}
    {page && nextOffset.current < page.total && <Button size="sm" variant="secondary" disabled={disabled || loading} loading={loading} onClick={() => void more()}>Load more material</Button>}
    {(error || selectionError) && <p role="alert" className="text-xs text-danger">{error || selectionError} <Button size="sm" variant="ghost" onClick={() => setRetry(value => value + 1)}>Retry</Button></p>}
  </div>;
}
