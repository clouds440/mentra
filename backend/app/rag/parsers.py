"""Thin RAG adapter over shared Mentra Documents; no format-reader implementation."""
from app.documents import DocumentReadError, create_document_reader
from app.rag.errors import ExtractionError


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class NativeDocumentParser:
    def __init__(self, reader=None):
        self.reader = reader if reader is not None else create_document_reader()
        self.version = self.reader.version

    def detect(self, path, filename):
        try:
            return self.reader.detect(path, filename)
        except DocumentReadError as exc:
            raise ExtractionError(str(exc)) from exc

    def capabilities(self):
        return self.reader.capabilities()

    def parse(self, path, media_type, max_pages, timeout):
        try:
            return self.reader.parse(path, media_type, max_pages, timeout)
        except DocumentReadError as exc:
            raise ExtractionError(str(exc)) from exc
