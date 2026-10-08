from pathlib import Path
from app.documents.errors import DocumentReadError
from app.documents.formats import CODE_FORMATS


class TextReader:
    formats = ('txt',)
    def available(self):
        return True

    def read(self, path: Path, kind: str, max_pages: int):
        text = path.read_text(encoding='utf-8-sig')
        if '\x00' in text:
            raise DocumentReadError('Binary content cannot be parsed as text.')
        return dict(blocks=[dict(text=p) for p in text.split('\n\n') if p.strip()], warnings=[])


class CodeReader:
    formats = CODE_FORMATS
    def available(self):
        return True

    def read(self, path: Path, kind: str, max_pages: int):
        with path.open(encoding='utf-8-sig', newline='') as source:
            text = source.read()
        if '\x00' in text:
            raise DocumentReadError('Binary content cannot be parsed as text.')
        return dict(blocks=[dict(text=text, method='native', language=kind)], warnings=[])
