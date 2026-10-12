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
        if self._image_media(data):
            from app.vision.chat_images import prepare_chat_image
            prepare_chat_image(data)
            return self.repository.create(owner, filename, data)
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
        if row['extraction'] is not None and row['extraction'].get('reader_revision') != 'chat-image-direct-v1':
            return row['extraction']
        with TemporaryDirectory(prefix='mentra-chat-') as directory:
            path = Path(directory) / 'source'
            path.write_bytes(row['data'])
            reader_filename = row['filename']
            if self._image_media(row['data']) in ('image/gif', 'image/webp'):
                from PIL import Image, ImageOps
                with Image.open(path) as image:
                    converted = ImageOps.exif_transpose(image).convert('RGB')
                    path = Path(directory) / 'source.png'
                    converted.save(path)
                reader_filename = 'source.png'
            try:
                result = self.reader.read(path, filename=reader_filename)
            except DocumentReadError as error:
                self.repository.extraction_failed(owner, identifier, str(error))
                raise AppError('CHAT_DOCUMENT_UNREADABLE', str(error), 422) from None
        extracted = dict(id=identifier, filename=row['filename'], format=result.format, media_type=result.media_type,
                         blocks=result.blocks, warnings=result.warnings, reader_revision=result.reader_revision)
        self.repository.save_extraction(owner, identifier, conversation_id, extracted)
        return extracted

    def image_input(self, owner, identifier, conversation_id):
        """Authorize first, then prepare raster bytes; documents retain their reader."""
        row = self.repository.read(owner, identifier, conversation_id)
        media = self._image_media(row['data']) or 'application/octet-stream'
        if not media.startswith('image/'):
            return None
        from app.vision.chat_images import prepare_chat_image
        block = prepare_chat_image(row['data'])
        if row['extraction'] is None:
            self.repository.save_extraction(owner, identifier, conversation_id, dict(
                id=identifier, filename=row['filename'], format=media.split('/')[1], media_type=media,
                blocks=[], warnings=[], reader_revision='chat-image-direct-v1'))
        return dict(id=identifier, filename=row['filename'], block=block)

    def add_to_library(self, owner, identifier, conversation_id, context_ids, rag):
        from io import BytesIO
        row = self.repository.read(owner, identifier, conversation_id)
        if row['library_result']:
            return row['library_result']
        if row['extraction'] and row['extraction'].get('reader_revision') == 'chat-image-direct-v1':
            self.extract(owner, identifier, conversation_id)
            row = self.repository.read(owner, identifier, conversation_id)
        if row['extraction'] is None:
            raise AppError('CHAT_EXTRACTION_PENDING', 'Wait until the file has been read before adding it to Library.', 409)
        result = rag.accept_extracted(owner, source=BytesIO(row['data']), filename=row['filename'],
            title=row['filename'], context_ids=context_ids, key='chat-attachment:' + identifier, extracted=row['extraction'])
        self.repository.link_library(owner, identifier, result)
        return result

    def original(self, owner, identifier, conversation_id):
        row = self.repository.read(owner, identifier, conversation_id)
        data = row['data']
        # Only recognized raster bytes may render inline. Documents/HTML/SVG
        # remain downloads, independent of the untrusted filename extension.
        media = self._image_media(data) or 'application/octet-stream'
        return dict(data=data, media_type=media, filename=row['filename'])

    @staticmethod
    def _image_media(data):
        if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
        if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
        if data.startswith((b'GIF87a', b'GIF89a')): return 'image/gif'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'image/webp'
        return None

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
