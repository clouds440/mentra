export interface LearningContext { context_id: string; name: string; status: 'ACTIVE' | 'RELATED' | 'DORMANT' | 'ARCHIVED' }
export interface MaterialJob { id: string; document_id: string; generation_id: string | null; operation: string; state: string; stage: string; attempts: number; error: string | null }
export interface MaterialVersion { id: string; filename: string; media_type: string; size_bytes: number; created_at: string; generation_id?: string | null; warnings?: string[] }
export interface MaterialGeneration { id: string; version_id: string; state: string; warnings: string[]; chunk_count: number }
export interface MaterialDocument {
  id: string; title: string; filename: string; context_ids: string[]; archived: boolean; revision: number;
  active_generation_id: string | null; versions: MaterialVersion[]; version_count: number; generations: MaterialGeneration[]; jobs: MaterialJob[];
}
export interface MaterialList { items: MaterialDocument[]; total: number; offset: number; limit: number }
export interface UploadResult { document_id: string; generation_id: string; job_id: string; duplicate: boolean }
export interface RAGCapabilities { formats: string[]; max_upload_bytes: number; max_pages: number; image_ocr: boolean; scanned_pdf_ocr: boolean; hybrid: boolean; reranking: boolean }
export interface SourceSpan { page: number | null; slide: number | null; block: number; start: number; end: number; method: string }
export interface SourceReference {
  token: string; document_id: string; version_id: string; generation_id: string; chunk_id: string;
  title: string; heading_path: string[]; spans: SourceSpan[]; excerpt: string; warnings: string[]; include_archived?: boolean;
}
export interface SourceChunk { id: string; content: string; heading_path: string[]; spans: SourceSpan[] }
export interface ChatSelection { mode: 'STANDARD' | 'SOURCE_SPECIFIC' | 'CROSS_CONTEXT'; document_ids?: string[]; context_ids?: string[]; include_archived?: boolean }
