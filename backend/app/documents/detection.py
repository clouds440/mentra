"""Content signatures first, with bounded streaming UTF-8 validation for text."""
import codecs
import zipfile
from pathlib import Path
from app.documents.errors import DocumentReadError
from app.documents.formats import CODE_FORMATS, format_for_filename


def validate_utf8(path: Path) -> None:
    decoder = codecs.getincrementaldecoder('utf-8-sig')()
    try:
        with path.open('rb') as source:
            while data := source.read(64 * 1024):
                decoder.decode(data)
            decoder.decode(b'', final=True)
    except UnicodeError as exc:
        raise DocumentReadError('Text files must use UTF-8 encoding.') from exc


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='success')
def detect_format(path: Path, filename: str, available: list[str]) -> str:
    with path.open('rb') as source:
        prefix = source.read(16)
    extension = format_for_filename(filename)
    if prefix.startswith(b'%PDF-'):
        kind = 'pdf'
    elif prefix.startswith(b'\x89PNG\r\n\x1a\n'):
        kind = 'png'
    elif prefix.startswith(b'\xff\xd8\xff'):
        kind = 'jpg'
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
                raise DocumentReadError('Compressed material exceeds the extraction limit.')
            names = {entry.filename for entry in entries}
            kind = 'docx' if 'word/document.xml' in names else 'pptx' if 'ppt/presentation.xml' in names else ''
    elif extension in ('txt', 'html', *CODE_FORMATS):
        kind = extension
        validate_utf8(path)
        if b'\x00' in prefix:
            raise DocumentReadError('Binary files cannot be uploaded as text.')
    else:
        kind = ''
    if kind not in available:
        raise DocumentReadError('This file format is unsupported on this server.')
    return kind
