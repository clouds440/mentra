import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText } from 'lucide-react';
import { getChatAttachment, saveChatAttachment } from '../../services/chatAttachments';
import type { AttachmentDetail, ChatAttachment } from '../../services/chatAttachments';
import { createContext, listContexts } from '../../services/rag';
import type { LearningContext } from '../../types/rag';
import { Button, Input, Select } from '../ui';

export function ChatAttachmentCard({ file, conversationId }: { file: ChatAttachment; conversationId: string }) {
  const [detail, setDetail] = useState<AttachmentDetail>();
  const [choosing, setChoosing] = useState(false), [busy, setBusy] = useState(false);
  const [contexts, setContexts] = useState<LearningContext[]>([]), [context, setContext] = useState('');
  const [error, setError] = useState<string>();
  const [newContext, setNewContext] = useState('');
  const action = useRef<AbortController | null>(null);
  useEffect(() => () => action.current?.abort(), [file.id, conversationId]);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>, retries = 0;
    async function refresh() {
      try {
        const value = await getChatAttachment(file.id, conversationId, controller.signal);
        if (controller.signal.aborted) return;
        setDetail(value);
        if (!value.ready && !value.error && retries++ < 80) timer = setTimeout(() => void refresh(), 2000);
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : 'File unavailable.');
          if (retries++ < 4) timer = setTimeout(() => void refresh(), 2000);
        }
      }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [file.id, conversationId]);
  async function choose() {
    action.current?.abort(); const controller = new AbortController(); action.current = controller;
    setChoosing(true); setError(undefined);
    try { const result = await listContexts(controller.signal); if (!controller.signal.aborted) setContexts(result.filter(item => item.status !== 'ARCHIVED')); }
    catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not load learning contexts.'); }
  }
  async function save() {
    action.current?.abort(); const controller = new AbortController(); action.current = controller;
    setBusy(true); setError(undefined);
    try {
      const result = await saveChatAttachment(file.id, conversationId, [context], controller.signal);
      if (!controller.signal.aborted) { setDetail(value => value && ({ ...value, library_result: result })); setChoosing(false); }
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not save this file.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function addContext() {
    action.current?.abort(); const controller = new AbortController(); action.current = controller;
    setBusy(true); setError(undefined);
    try {
      const result = await createContext(newContext.trim(), true, controller.signal);
      if (!controller.signal.aborted) { setContexts(previous => [...previous, result]); setContext(result.context_id); setNewContext(''); }
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Could not create learning context.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <div className="mt-3 rounded-xl border border-border bg-surface p-3 text-sm">
    <div className="flex items-center gap-2"><FileText aria-hidden="true" size={16} /><span className="break-all font-medium">{file.filename}</span></div>
    <p className="mt-1 text-xs text-muted">{detail?.ready ? 'Content extracted' : detail?.error ? 'Could not read this file' : 'Waiting for file extraction'}</p>
    {detail?.warnings.map((warning, index) => <p key={index} className="mt-1 text-xs text-muted">{warning}</p>)}
    {detail?.library_result ? <Link className="mt-2 inline-block text-accent underline" to={`/library/${detail.library_result.document_id}`}>View in Library · processing status</Link>
      : choosing ? <div className="mt-2 space-y-2">
        <Select aria-label={`Learning context for ${file.filename}`} value={context} onChange={event => setContext(event.target.value)} disabled={busy}>
          <option value="">Choose learning context</option>{contexts.map(item => <option key={item.context_id} value={item.context_id}>{item.name}</option>)}
        </Select>
        <div className="flex flex-wrap gap-2"><Input className="min-w-32 flex-1" aria-label={`New learning context for ${file.filename}`} placeholder="Or create a learning context" value={newContext} maxLength={100} disabled={busy} onChange={event => setNewContext(event.target.value)} /><Button size="sm" variant="secondary" disabled={busy || !newContext.trim()} onClick={() => void addContext()}>Create context</Button></div>
        <div className="flex gap-2"><Button size="sm" disabled={!context || busy} onClick={() => void save()}>{busy ? 'Adding…' : 'Add extracted content'}</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setChoosing(false)}>Not now</Button></div>
      </div> : <Button className="mt-2" size="sm" variant="ghost" disabled={!detail?.ready} onClick={() => void choose()}>Add to Library</Button>}
    {(error || detail?.error) && <p className="mt-2 text-xs text-danger" role="alert">{error || detail?.error}</p>}
  </div>;
}
