import { useCallback, useEffect, useRef, useState } from 'react';
import { Brain, Plus, Search } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Spinner } from '../ui/Spinner';
import { Toggle } from '../ui/Toggle';
import { memoryApi } from '../../services/memories';
import type { MemoryPreferences, UserMemory } from '../../types/memories';
import { MemoryEditor } from './MemoryEditor';
import { MemoryDetails } from './MemoryDetails';
import { MemoryList } from './MemoryList';
import { MemoryConfirmation } from './MemoryConfirmation';
import { ApiError } from '../../services/api';

export function MemoriesSettings({ active }: { active: boolean }) {
  const { identity } = useAuth();
  return <AccountMemories key={identity?.learner_id} owner={identity?.learner_id ?? ''} active={active} />;
}

function AccountMemories({ owner, active }: { owner: string; active: boolean }) {
  const [params] = useSearchParams();
  const [items, setItems] = useState<UserMemory[]>([]);
  const [prefs, setPrefs] = useState<MemoryPreferences>();
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [editor, setEditor] = useState<UserMemory | 'new'>();
  const [detail, setDetail] = useState<UserMemory>();
  const [deleting, setDeleting] = useState<UserMemory>();
  const [resolving, setResolving] = useState<UserMemory>();
  const [conflictDraft, setConflictDraft] = useState<string>();
  const [refresh, setRefresh] = useState(0);
  const channel = useRef<BroadcastChannel>();
  const mounted = useRef(true);
  const requestId = useRef(crypto.randomUUID());
  const requestPayload = useRef('');
  const paging = useRef(false);
  const listEpoch = useRef(0);
  const pageRequest = useRef<AbortController>();
  const detailRequest = useRef<AbortController>();
  const mutating = useRef(false);
  const fetchKey = useRef('');
  const detailId = useRef<string>();
  detailId.current = detail?.id;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; pageRequest.current?.abort(); detailRequest.current?.abort(); }; }, []);
  useEffect(() => { const timer = setTimeout(() => setSearch(query), 250); return () => clearTimeout(timer); }, [query]);
  useEffect(() => {
    const bc = new BroadcastChannel(`mentra-memory-${owner}`);
    channel.current = bc;
    bc.onmessage = () => setRefresh(value => value + 1);
    const focus = () => { if (active) setRefresh(value => value + 1); };
    window.addEventListener('focus', focus);
    return () => { bc.close(); channel.current = undefined; window.removeEventListener('focus', focus); };
  }, [owner, active]);
  useEffect(() => {
    listEpoch.current++;
    pageRequest.current?.abort();
    paging.current = false;
    if (!active || busy) { setLoading(false); return; }
    const key = JSON.stringify([search, status, refresh]);
    if (fetchKey.current === key) return;
    const controller = new AbortController();
    setLoading(true); setError('');
    Promise.all([memoryApi.list(search, status, undefined, controller.signal), memoryApi.preferences(controller.signal)])
      .then(async ([page, preferences]) => { if (!controller.signal.aborted) {
        fetchKey.current = key; setItems(page.items); setCursor(page.next_cursor); setPrefs(preferences); setLoaded(true);
        if (detailId.current) {
          const id = detailId.current;
          try { const value = await memoryApi.detail(id, controller.signal); if (!controller.signal.aborted && detailId.current === id) setDetail(value); }
          catch (cause) { if (!controller.signal.aborted && cause instanceof ApiError && cause.status === 404) { setDetail(undefined); setNotice('The selected memory was deleted.'); } }
        }
      } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [active, search, status, refresh, busy]);
  const openDetails = useCallback(async (id: string) => {
    detailRequest.current?.abort();
    const controller = new AbortController();
    detailRequest.current = controller;
    setError('');
    try { const value = await memoryApi.detail(id, controller.signal); if (mounted.current && !controller.signal.aborted) setDetail(value); }
    catch (cause) { if (mounted.current && !controller.signal.aborted) setError((cause as Error).message); }
  }, []);
  useEffect(() => { const id = params.get('memory'); if (active && id) void openDetails(id); }, [active, params, openDetails]);

  function merge(value: UserMemory) {
    setItems(previous => {
      const rest = previous.filter(item => item.id !== value.id);
      // Membership may change after an edit; do not retain a row in the wrong filter.
      return (!status || value.status === status) && (!search || value.content.toLowerCase().includes(search.toLowerCase()))
        ? [value, ...rest].slice(0, 50) : rest;
    });
    setCursor(previous => previous ? 'reset' : null); // Reset on next pagination, not a full-list fetch after each write.
    if (detail?.id === value.id) setDetail(previous => previous ? { ...previous, ...value } : value);
    channel.current?.postMessage({ changed: true });
  }
  async function mutate(action: () => Promise<void>) {
    if (mutating.current) return;
    mutating.current = true;
    setBusy(true); setError(''); setNotice('');
    try { await action(); }
    catch (cause) {
      if (mounted.current) {
        setError((cause as Error).message);
        if (cause instanceof ApiError && (cause.code === 'MEMORY_CONFLICT' || cause.status === 404)) {
          // Reconcile stale preferences/list rows and dialog revisions. Require
          // another explicit click after displaying the freshly loaded statement.
          setRefresh(value => value + 1);
          setNotice('Another session changed your memory settings or records. Current values have been reloaded; review them before trying again.');
          const selected = deleting ?? resolving;
          if (selected) {
            const latest = await memoryApi.detail(selected.id).catch(() => undefined);
            if (mounted.current) {
              if (deleting) setDeleting(latest);
              if (resolving) setResolving(latest?.status === 'conflict' ? latest : undefined);
              setNotice(latest ? 'This memory changed. Review the current statement before trying again.' : 'This memory is no longer available.');
            }
          }
        }
        if (cause instanceof ApiError && cause.code === 'MEMORY_CONFLICT' && editor && editor !== 'new') {
          // Keep the user's draft mounted while obtaining a new revision.
          const latest = await memoryApi.detail(editor.id).catch(() => undefined);
          if (latest && mounted.current) { setEditor(latest); setDetail(latest); setNotice(`Latest saved version: ${latest.content}. Your draft is still in the editor; review before saving again.`); }
        }
      }
    } finally { mutating.current = false; if (mounted.current) setBusy(false); }
  }
  async function more() {
    if (!cursor || paging.current) return;
    const epoch = listEpoch.current;
    const controller = new AbortController();
    pageRequest.current = controller;
    paging.current = true; setLoading(true);
    try { const page = await memoryApi.list(search, status, cursor === 'reset' ? undefined : cursor, controller.signal); if (mounted.current && !controller.signal.aborted && epoch === listEpoch.current) { setItems(previous => cursor === 'reset' || previous.length >= 90 ? page.items : [...previous, ...page.items.filter(item => !previous.some(old => old.id === item.id))]); setCursor(page.next_cursor); } }
    catch (cause) { if (mounted.current && !controller.signal.aborted && epoch === listEpoch.current) setError((cause as Error).message); }
    finally { if (epoch === listEpoch.current) { paging.current = false; if (mounted.current) setLoading(false); } }
  }
  return <section aria-label="Memories" className="mt-7 space-y-6">
    <div className="flex flex-col items-start justify-between gap-4 sm:flex-row"><div className="min-w-0"><div className="flex items-center gap-2"><Brain className="text-accent" size={20} aria-hidden="true" /><h2 className="text-xl font-medium text-heading">Your memories</h2></div><p className="mt-2 text-sm leading-6 text-muted">Control what Mentra remembers about you. Memories are retrieved when useful, and stay saved when you delete a chat.</p></div><Button size="sm" variant="secondary" className="shrink-0 whitespace-nowrap" onClick={() => { requestId.current = crypto.randomUUID(); requestPayload.current = ''; setEditor('new'); }} disabled={!!editor}><Plus size={16} aria-hidden="true" />Add memory</Button></div>
    {prefs && <div className="rounded-xl border border-border p-4"><Toggle label="Let Mentra save useful memories" description="Only explicit statements can be saved automatically. Inferences need your confirmation. Sensitive details require a specific request to remember them. Turning this off keeps existing memories available for recall." checked={prefs.automatic_memory} disabled={busy || loading} onChange={event => { const previous = prefs; const checked = event.target.checked; setPrefs({ ...prefs, automatic_memory: checked }); void mutate(async () => { try { const value = await memoryApi.configure(checked, previous.revision); if (mounted.current) { setPrefs(value); channel.current?.postMessage({ changed: true }); } } catch (cause) { if (mounted.current) setPrefs(previous); throw cause; } }); }} /></div>}
    {error && <div role="alert" className="rounded-lg border border-border p-3 text-sm text-foreground">{error}<Button variant="ghost" size="sm" onClick={() => setRefresh(value => value + 1)}>Reload memories</Button></div>}
    {notice && <p role="status" className="text-sm text-muted">{notice}</p>}
    {editor && <MemoryEditor key={editor === 'new' ? 'new' : editor.id} memory={editor === 'new' ? undefined : editor} busy={busy} onCancel={() => setEditor(undefined)} onSave={async (content, category) => mutate(async () => {
      if (editor !== 'new' && editor.status === 'conflict') {
        const latest = await memoryApi.detail(editor.id);
        if (mounted.current) { setResolving(latest); setConflictDraft(content); }
        return; // Save the correction only after reviewing the other statements.
      }
      const payload = JSON.stringify([content, category]);
      if (requestPayload.current !== payload) { requestId.current = crypto.randomUUID(); requestPayload.current = payload; }
      const value = editor === 'new' ? (await memoryApi.create(content, category, requestId.current)).memory : await memoryApi.edit(editor, { content });
      if (mounted.current) { merge(value); setEditor(undefined); setNotice('Memory saved.'); }
    })} />}
    <Button variant="ghost" size="sm" disabled={loading} onClick={() => setRefresh(value => value + 1)}>Refresh memories</Button><div className="flex flex-col gap-3 sm:flex-row"><label className="relative flex-1"><span className="sr-only">Search memories</span><Search aria-hidden="true" className="absolute left-3 top-3.5 text-subtle" size={16} /><Input className="pl-9" placeholder="Search your memories" disabled={busy} value={query} onChange={event => setQuery(event.target.value)} maxLength={300} /></label><label><span className="sr-only">Memory status</span><Select disabled={busy} value={status} onChange={event => { setItems([]); setLoading(true); setStatus(event.target.value); }}><option value="">All memories</option><option value="active">Saved</option><option value="pending">Needs confirmation</option><option value="conflict">Conflicting</option></Select></label></div>
    {loading && <div role="status" className="flex items-center gap-2 text-sm text-muted"><Spinner />Loading memories…</div>}
    {loaded && !loading && items.length === 0 && <div className="rounded-xl border border-dashed border-border py-10 text-center"><p className="text-heading">{search || status ? 'No matching memories' : 'A fresh start'}</p><p className="mt-2 text-sm text-muted">{search || status ? 'Try another search or status.' : 'Add a memory yourself, or ask Mentra to remember something useful.'}</p></div>}
    <MemoryList items={items} busy={busy} editing={!!editor} onEvidence={item => void openDetails(item.id)} onEdit={setEditor} onConfirm={item => void mutate(async () => merge(await memoryApi.edit(item, { confirm: true, clear_expiration: true })))} onResolve={item => { setError(''); void memoryApi.detail(item.id).then(value => { if (mounted.current) { if (value.status === 'conflict') { setConflictDraft(undefined); setResolving(value); } else { setRefresh(previous => previous + 1); setNotice('This conflict was already resolved.'); } } }).catch(cause => { if (mounted.current) setError(cause.message); }); }} onPin={item => void mutate(async () => merge(await memoryApi.edit(item, { pinned: !item.pinned })))} onDelete={setDeleting} />
    {cursor && <Button variant="secondary" disabled={loading} onClick={() => void more()}>Load more memories</Button>}
    {detail && <section aria-label="Memory evidence" className="rounded-xl border border-border p-4"><div className="mb-4 flex items-center justify-between"><h3 className="font-medium text-heading">Supporting evidence</h3><Button variant="ghost" size="sm" onClick={() => { detailRequest.current?.abort(); setDetail(undefined); }}>Close evidence</Button></div><MemoryDetails memory={detail} /></section>}
    {resolving && <MemoryConfirmation title="Resolve memory conflict" busy={busy} error={error} onCancel={() => { setResolving(undefined); setConflictDraft(undefined); }}><p id="memory-conflict-description" className="text-sm leading-6 text-body">Keep this statement as current? The conflicting statements below will require review and will be excluded from recall.</p><p className="mt-3 text-sm font-medium text-heading">{conflictDraft ?? resolving.content}</p><ul className="mt-3 space-y-2 text-sm text-muted">{resolving.conflicts.map(item => <li key={item.memory_id}>{item.content}</li>)}</ul><div className="mt-4 flex gap-2"><Button disabled={busy} onClick={() => void mutate(async () => { const value = await memoryApi.edit(resolving, { confirm: true, resolve_conflict: true, ...(conflictDraft !== undefined ? { content: conflictDraft } : {}), conflict_revisions: Object.fromEntries(resolving.conflicts.map(item => [item.memory_id, item.revision])) }); if (mounted.current) { merge(value); if (editor !== 'new' && editor?.id === value.id) setEditor(undefined); setResolving(undefined); setConflictDraft(undefined); setRefresh(previous => previous + 1); setNotice('Conflict resolved. Other statements now require review.'); } })}>Keep this statement</Button><Button variant="ghost" disabled={busy} onClick={() => { setResolving(undefined); setConflictDraft(undefined); }}>Cancel review</Button></div></MemoryConfirmation>}
    {deleting && <MemoryConfirmation title="Delete memory" busy={busy} error={error} onCancel={() => setDeleting(undefined)}><p id="memory-delete-description" className="text-sm leading-6 text-body">Delete this memory and its saved evidence? Its original chat messages remain. Mentra will not automatically save it again from the same evidence.</p><p className="mt-3 whitespace-pre-wrap break-words text-sm font-medium text-heading">{deleting.content}</p><div className="mt-4 flex gap-2"><Button disabled={busy} onClick={() => void mutate(async () => { await memoryApi.remove(deleting); if (mounted.current) { setItems(previous => previous.filter(item => item.id !== deleting.id)); if (detail?.id === deleting.id) setDetail(undefined); if (editor !== 'new' && editor?.id === deleting.id) setEditor(undefined); setDeleting(undefined); setCursor(previous => previous ? 'reset' : null); channel.current?.postMessage({ changed: true }); setNotice('Memory deleted.'); requestAnimationFrame(() => document.getElementById('settings-tab-memories')?.focus()); } })}>Confirm deletion</Button><Button variant="ghost" autoFocus disabled={busy} onClick={() => setDeleting(undefined)}>Keep memory</Button></div></MemoryConfirmation>}
    <p className="text-xs leading-5 text-subtle">A saved statement may become outdated. Review dates and evidence before confirming it. Mentra never treats pending or conflicting memories as established facts. Automatic limits: {prefs?.active_limit ?? 200} current memories and {prefs?.pending_limit ?? 50} candidates. Account capacity: {prefs?.manual_limit ?? 1000} memories. Nothing is silently removed to make space.</p>
  </section>;
}
