"""One-off chat files use the shared Documents facade (including Vision OCR)."""
from pathlib import Path
from tempfile import TemporaryDirectory
from app.core.exceptions import AppError
from app.documents import create_document_reader, DocumentReadError


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class AttachmentService:
    def __init__(self, repository, reader=None, maximum=25 * 1024 * 1024):
        self.repository, self.reader, self.maximum = repository, reader or create_document_reader(), maximum

    def upload(self, owner, stream, filename):
        filename = Path((filename or 'attachment').replace('\\', '/')).name[:200]
        data = stream.read(self.maximum + 1)
        if not data:
            raise AppError('CHAT_EMPTY_FILE', 'Choose a non-empty file.', 422)
        if len(data) > self.maximum:
            raise AppError('CHAT_FILE_TOO_LARGE', 'This file exceeds the upload size limit.', 413)
        with TemporaryDirectory(prefix='mentra-chat-check-') as directory:
            path = Path(directory) / 'source'
            path.write_bytes(data)
            try:
                self.reader.detect(path, filename)
            except DocumentReadError as error:
                raise AppError('CHAT_UNSUPPORTED_FILE', str(error), 422) from None
        return self.repository.create(owner, filename, data)

    def extract(self, owner, identifier, conversation_id):
        row = self.repository.read(owner, identifier, conversation_id)
        if row['extraction'] is not None:
            return row['extraction']
        with TemporaryDirectory(prefix='mentra-chat-') as directory:
            path = Path(directory) / 'source'
            path.write_bytes(row['data'])
            try:
                result = self.reader.read(path, filename=row['filename'])
            except DocumentReadError as error:
                self.repository.extraction_failed(owner, identifier, str(error))
                raise AppError('CHAT_DOCUMENT_UNREADABLE', str(error), 422) from None
        extracted = dict(id=identifier, filename=row['filename'], format=result.format, media_type=result.media_type,
                         blocks=result.blocks, warnings=result.warnings, reader_revision=result.reader_revision)
        self.repository.save_extraction(owner, identifier, conversation_id, extracted)
        return extracted

    def add_to_library(self, owner, identifier, conversation_id, context_ids, rag):
        from io import BytesIO
        row = self.repository.read(owner, identifier, conversation_id)
        if row['library_result']:
            return row['library_result']
        if row['extraction'] is None:
            raise AppError('CHAT_EXTRACTION_PENDING', 'Wait until the file has been read before adding it to Library.', 409)
        result = rag.accept_extracted(owner, source=BytesIO(row['data']), filename=row['filename'],
            title=row['filename'], context_ids=context_ids, key='chat-attachment:' + identifier, extracted=row['extraction'])
        self.repository.link_library(owner, identifier, result)
        return result

    @staticmethod
    def context(extracted, query, maximum=8000):
        """Bound model input; preserve source locations and explicitly disclose selection."""
        import re
        words = set(re.findall(r'\w{3,}', query.casefold()))
        blocks = extracted['blocks']
        ranked = sorted(enumerate(blocks), key=lambda item: (-sum(word in item[1]['text'].casefold() for word in words), item[0]))
        chosen, remaining = [], maximum
        for index, block in ranked:
            if remaining <= 0:
                break
            text = block['text'][:min(remaining, 3000)]
            chosen.append((index, dict(block, text=text)))
            remaining -= len(text)
        selected = [block for _, block in sorted(chosen)]
        return dict(id=extracted['id'], filename=extracted['filename'], blocks=selected,
            warnings=extracted['warnings'], partial=sum(len(x['text']) for x in selected) < sum(len(x['text']) for x in blocks))
