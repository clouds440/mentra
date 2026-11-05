export type PanelResource =
  | { kind: 'web'; title: string; url: string }
  | { kind: 'library'; title: string; document_id: string; version_id?: string; generation_id?: string; chunk_id?: string }
  | { kind: 'attachment'; title: string; conversation_id: string; file_id: string }
  | { kind: 'history'; title: string; conversation_id: string; sequence: number }
  | { kind: 'memory'; title: string; memory_id: string; revision: number };

export type SourceAnnotation =
  | { mode?: never; source: PanelResource | { kind: 'chat'; title: 'Mentra response' | 'Your message' }; text: string }
  | { mode: 'page'; source: Extract<PanelResource, { kind: 'web' }> };
export interface PinnedSource { id: string; source: PanelResource }

export function resourceKey(source: PanelResource) {
  switch (source.kind) {
    case 'web': return JSON.stringify([source.kind, source.url]);
    case 'library': return JSON.stringify([source.kind, source.document_id, source.version_id, source.generation_id, source.chunk_id]);
    case 'attachment': return JSON.stringify([source.kind, source.conversation_id, source.file_id]);
    case 'history': return JSON.stringify([source.kind, source.conversation_id, source.sequence]);
    case 'memory': return JSON.stringify([source.kind, source.memory_id, source.revision]);
  }
}
