"""One-off chat files use the shared Documents facade (including Vision OCR)."""
from pathlib import Path
from tempfile import TemporaryDirectory
from app.core.exceptions import AppError
from app.documents import create_document_reader, DocumentReadError


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class AttachmentService:
    def __init__(self, repository, reader=None, maximum=25 * 1024 * 1024, admission=None, files=None):
        self.repository, self.reader, self.maximum = repository, reader or create_document_reader(), maximum
        self.admission = admission
        self.files = files or repository.files

    def attach(self, owner, file_id):
        file=self.files.metadata(owner,file_id,'chat')
        return self.repository.create(owner,file['filename'],file)

    def extract(self, owner, identifier, conversation_id):
        if self.admission:
            with self.admission.reserve('parse', owner, capacity=4, owner_capacity=1, seconds=600):
                return self._extract(owner, identifier, conversation_id)
        return self._extract(owner, identifier, conversation_id)

    def _extract(self, owner, identifier, conversation_id):
        row = self.repository.read(owner, identifier, conversation_id)
        if row['extraction'] is not None and row['extraction'].get('reader_revision') != 'chat-image-direct-v1':
            return row['extraction']
        with self.files.materialize(owner,row['file_id']) as path, TemporaryDirectory(prefix='mentra-chat-') as directory:
            reader_filename = row['filename']
            if row['media_type'] in ('image/gif', 'image/webp'):
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
        media = row['media_type']
        if not media.startswith('image/'):
            return None
        from app.vision.chat_images import prepare_chat_image
        block = prepare_chat_image(self.files.read(owner,row['file_id']))
        if row['extraction'] is None:
            self.repository.save_extraction(owner, identifier, conversation_id, dict(
                id=identifier, filename=row['filename'], format=media.split('/')[1], media_type=media,
                blocks=[], warnings=[], reader_revision='chat-image-direct-v1'))
        return dict(id=identifier, filename=row['filename'], block=block)

    def add_to_library(self, owner, identifier, conversation_id, context_ids, rag):
        row = self.repository.read(owner, identifier, conversation_id)
        if row['library_result']:
            self._validate_library_result(owner, row['library_result'], context_ids, rag)
            return row['library_result']
        if row['extraction'] and row['extraction'].get('reader_revision') == 'chat-image-direct-v1':
            self.extract(owner, identifier, conversation_id)
            row = self.repository.read(owner, identifier, conversation_id)
        if row['extraction'] is None:
            raise AppError('CHAT_EXTRACTION_PENDING', 'Wait until the file has been read before adding it to Library.', 409)
        result = rag.accept_extracted(owner, file_id=row['file_id'], filename=row['filename'],
            title=row['filename'], context_ids=context_ids, key='chat-attachment:' + identifier, extracted=row['extraction'])
        self._validate_library_result(owner, result, context_ids, rag)
        self.repository.link_library(owner, identifier, result)
        return result

    @staticmethod
    def _validate_library_result(owner, result, context_ids, rag):
        contexts = rag.validate_contexts(owner, context_ids)
        try:
            document = rag.get_document(owner, result['document_id'])
        except AppError as error:
            if error.status_code != 404:
                raise
            raise AppError('CHAT_LIBRARY_TARGET_DELETED', 'This Library material was deleted. Upload it again to create new material.', 409) from None
        if set(document['context_ids']) != set(contexts):
            raise AppError('CHAT_LIBRARY_CONTEXT_CHANGED', 'This file was already added with different learning contexts.', 409)

    def original(self, owner, identifier, conversation_id):
        row = self.repository.read(owner, identifier, conversation_id)
        return dict(file_id=row['file_id'],binding_id=self.files.binding(owner,row['file_id'],'chat',dict(chat_attachment_id=identifier)))

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
