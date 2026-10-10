"""One document facade over independent engines, without consuming-domain imports."""
from importlib.metadata import version as package_version, PackageNotFoundError
from pathlib import Path
from functools import cached_property
from app.documents.detection import detect_format
from app.documents.errors import DocumentReadError
from app.documents.formats import MEDIA
from app.documents.isolation import read_isolated
from app.documents.ports import FormatReader
from app.documents.schemas import DocumentContent, DocumentPayload

READER_VERSION = 'documents-native-vision-v3'


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class DocumentReader:
    def __init__(self, engines: list[FormatReader], vision, *, isolated: bool = False):
        self._engines = {}
        for engine in engines:
            for kind in engine.formats:
                if kind in self._engines or kind not in MEDIA:
                    raise ValueError(f'Duplicate or unknown document format: {kind}')
                self._engines[kind] = engine
        self._vision, self._isolated = vision, isolated

    @cached_property
    def version(self):
        assets = []
        for package in ('pypdf', 'python-docx', 'python-pptx', 'beautifulsoup4'):
            try:
                revision = package_version(package)
            except PackageNotFoundError:
                revision = 'unavailable'
            assets.append(f'{package}={revision}')
        assets.extend(f'{asset}={revision}' for asset, revision in self._vision.asset_revisions())
        return READER_VERSION + ':' + ';'.join(assets)

    def capabilities(self):
        engines = {id(engine): engine for engine in self._engines.values()}
        available = {key: engine.available() for key, engine in engines.items()}
        formats = [kind for kind, engine in self._engines.items() if available[id(engine)]]
        vision = self._vision.capabilities()
        return dict(formats=formats, image_ocr=vision.image_ocr, scanned_pdf_ocr=vision.pdf_page_ocr, parser_revision=self.version)

    def detect(self, path: Path, filename: str) -> str:
        return MEDIA[detect_format(Path(path), filename, self.capabilities()['formats'])]

    def read(self, path: Path, *, filename: str | None = None, max_pages: int = 200, timeout: int = 120,
             max_bytes: int = 25 * 1024 * 1024) -> DocumentContent:
        path = Path(path)
        self._limits(max_pages, timeout)
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise DocumentReadError('Document byte limit must be a positive integer.')
        if path.stat().st_size > max_bytes:
            raise DocumentReadError('Document exceeds the upload size limit.')
        media_type = self.detect(path, filename or path.name)
        payload = self.parse(path, media_type, max_pages, timeout)
        kind = next(kind for kind, media in MEDIA.items() if media == media_type)
        return DocumentContent(kind, media_type, payload['blocks'], payload['warnings'], self.version)

    def parse(self, path: Path, media_type: str, max_pages: int = 200, timeout: int = 120) -> DocumentPayload:
        self._limits(max_pages, timeout)
        kind = next((kind for kind, media in MEDIA.items() if media == media_type), None)
        if kind not in self._engines:
            raise DocumentReadError('This media type is unsupported by the document parser.')
        if self._isolated:
            with workflow_logger.step('app.documents.readers.' + kind, 'isolated.parse', input=dict(format=kind, max_pages=max_pages)) as step:
                result = read_isolated(Path(path), kind, max_pages, timeout)
                step.result(dict(block_count=len(result['blocks']), warning_count=len(result['warnings'])), 'success')
                return result
        return self.read_in_process(Path(path), kind, max_pages)

    def read_in_process(self, path: Path, kind: str, max_pages: int = 200) -> DocumentPayload:
        """Engine entry point for the isolated child or explicitly trusted callers."""
        self._limits(max_pages, 120)
        engine = self._engines.get(kind)
        if engine is None or not engine.available():
            raise DocumentReadError('This file format is unsupported on this server.')
        result = engine.read(Path(path), kind, max_pages)
        if sum(len(block['text']) for block in result['blocks']) > 5_000_000:
            raise DocumentReadError('Extracted text exceeds the processing limit. Split this material into smaller files.')
        if any('\x00' in block['text'] for block in result['blocks']):
            result['warnings'].append('Unsupported null characters were removed during extraction.')
            for block in result['blocks']:
                block['text'] = block['text'].replace('\x00', '')
        result['warnings'] = list(dict.fromkeys(result['warnings']))
        return result

    @staticmethod
    def _limits(max_pages, timeout):
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 1000:
            raise DocumentReadError('Document page limit must be an integer between 1 and 1000.')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 600:
            raise DocumentReadError('Document timeout must be between 0 and 600 seconds.')
