import { useEffect, useState } from 'react';
import { getMaterial, listVersions } from '../../services/rag';
import type { MaterialDocument, MaterialVersion } from '../../types/rag';
import type { PanelResource } from '../../types/sourceAnnotations';
import { ChatAttachmentPreview } from '../chat/ChatAttachmentPreview';
import { HistoryReferenceContent } from '../chat/HistoryReferenceViewer';
import { MaterialSourceTab } from '../library/MaterialSourceTab';
import { SourceReader } from '../library/SourceViewer';
import { Skeleton } from '../ui';
import { useSidePanelActions } from './sidePanelState';

export default function ReopenedSource({ source }: { source: Exclude<PanelResource, { kind: 'web' }> }) {
  const panel = useSidePanelActions();
  switch (source.kind) {
    case 'attachment': return <ChatAttachmentPreview filename={source.title} fileId={source.file_id} conversationId={source.conversation_id} />;
    case 'history':
    case 'memory': return <HistoryReferenceContent reference={{ token: '', ...source }} onClose={() => panel?.hide()} />;
    case 'library': return source.version_id && source.generation_id && source.chunk_id
      ? <SourceReader source={{ token: '', title: source.title, document_id: source.document_id, version_id: source.version_id,
        generation_id: source.generation_id, chunk_id: source.chunk_id, heading_path: [], spans: [], warnings: [], excerpt: '' }} />
      : <ReopenedMaterial source={source} />;
  }
}

function ReopenedMaterial({ source }: { source: Extract<PanelResource, { kind: 'library' }> }) {
  const [material, setMaterial] = useState<{ doc: MaterialDocument; version?: MaterialVersion } | null>();
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const doc = await getMaterial(source.document_id, controller.signal, true);
        let version = doc.versions.find(item => item.id === source.version_id);
        if (source.version_id && !version) {
          let offset = doc.versions.length;
          while (!version && !controller.signal.aborted) {
            const page = await listVersions(doc.id, offset, controller.signal);
            version = page.items.find(item => item.id === source.version_id);
            offset += page.items.length;
            if (!page.items.length || offset >= page.total) break;
          }
        }
        if (!controller.signal.aborted) setMaterial(source.version_id && !version ? null : { doc, version });
      } catch { if (!controller.signal.aborted) setMaterial(null); }
    })();
    return () => controller.abort();
  }, [source]);
  if (material === null) return <p className="p-4 text-sm text-muted" role="status">This material or version is no longer available.</p>;
  if (!material) return <Skeleton variant="text" className="p-4" />;
  return <MaterialSourceTab initial={material.doc} version={material.version} />;
}
