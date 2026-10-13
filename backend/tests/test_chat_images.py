import asyncio
import base64
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import httpx
from PIL import Image
from langchain_core.messages import AIMessage, HumanMessage
from openai import BadRequestError, AuthenticationError
from app.chat.attachments import AttachmentService
from app.chat.repositories.attachments import AttachmentRepository
from app.core.exceptions import AppError
from app.documents import DocumentContent
from app.langchain.chat_service import ChatService
from app.langchain.llm import MentraLLM
from app.langchain.image_fallback import chat_image_fallback, has_images
from app.langchain.orchestration_service import OrchestrationService
from app.langchain.prompts import PromptSource
from app.rag.schemas import ChatSelection
from app.vision.chat_images import prepare_chat_image


def raster(kind='PNG', size=(24, 16)):
    output = io.BytesIO()
    Image.new('RGB', size, 'red').save(output, format=kind)
    return output.getvalue()


class ChatImageTests(unittest.TestCase):
    def test_preparation_accepts_rasters_bounds_dimensions_and_preserves_original(self):
        for kind in ('PNG', 'JPEG', 'GIF', 'WEBP'):
            data = raster(kind, (2000, 1000))
            block = prepare_chat_image(data)
            with Image.open(io.BytesIO(base64.b64decode(block['image_url']['url'].split(',')[1]))) as image:
                self.assertEqual(image.size, (1600, 800))
            with Image.open(io.BytesIO(data)) as original:
                self.assertEqual(original.size, (2000, 1000))

    def test_invalid_and_oversized_images_reject_before_storage(self):
        repository = Mock()
        service = AttachmentService(repository, Mock())
        with self.assertRaises(AppError):
            service.upload('owner', io.BytesIO(b'\x89PNG\r\n\x1a\ninvalid'), 'bad.png')
        repository.create.assert_not_called()
        with patch('app.vision.chat_images.Image.open') as opened:
            opened.return_value.__enter__.return_value.format = 'PNG'
            opened.return_value.__enter__.return_value.width = 30_000_001
            opened.return_value.__enter__.return_value.height = 1
            with self.assertRaises(AppError) as error:
                prepare_chat_image(b'data')
            self.assertEqual(error.exception.code, 'CHAT_IMAGE_SIZE')

    def test_image_upload_does_not_depend_on_ocr_and_stores_original_bytes(self):
        repository, reader = Mock(), Mock()
        data = raster()
        AttachmentService(repository, reader).upload('owner', io.BytesIO(data), 'photo.png')
        reader.detect.assert_not_called()
        repository.create.assert_called_once_with('owner', 'photo.png', data)

    def test_owned_image_preparation_skips_ocr_and_documents_still_route_to_reader(self):
        repository, reader = Mock(), Mock()
        repository.read.return_value = dict(data=raster(), filename='photo.png', extraction=None)
        service = AttachmentService(repository, reader)
        self.assertEqual(service.image_input('owner', 'file', 'chat')['filename'], 'photo.png')
        repository.read.assert_called_with('owner', 'file', 'chat')
        reader.read.assert_not_called()
        self.assertEqual(repository.save_extraction.call_args.args[-1]['reader_revision'], 'chat-image-direct-v1')
        repository.read.return_value['data'] = b'notes'
        self.assertIsNone(service.image_input('owner', 'file', 'chat'))

    def test_direct_image_marker_does_not_poison_ocr_cache_or_library(self):
        repository, reader = Mock(), Mock()
        row = dict(data=raster(), filename='photo.png', extraction=dict(reader_revision='chat-image-direct-v1'), library_result=None)
        repository.read.side_effect = lambda *args: row.copy()
        repository.save_extraction.side_effect = lambda owner, identifier, chat, result: row.update(extraction=result)
        reader.read.return_value = DocumentContent('png', 'image/png', [dict(text='Original text', method='ocr')], [], 'ocr-v1')
        service = AttachmentService(repository, reader)
        rag = Mock()
        service.add_to_library('owner', 'file', 'chat', ['context'], rag)
        self.assertEqual(rag.accept_extracted.call_args.kwargs['extracted']['blocks'][0]['text'], 'Original text')
        service.extract('owner', 'file', 'chat')
        reader.read.assert_called_once()

    def test_three_image_limit_is_enforced_before_binding(self):
        session = Mock()
        rows = [dict(id=str(i), data=raster(), conversation_id=None, filename='photo.png', size_bytes=10) for i in range(4)]
        session.execute.return_value.mappings.return_value.all.return_value = rows
        with self.assertRaises(AppError) as error:
            AttachmentRepository.bind(session, 'owner', [str(i) for i in range(4)], 'chat')
        self.assertEqual(error.exception.code, 'CHAT_IMAGE_LIMIT')
        self.assertEqual(session.execute.call_count, 1)

    def test_chat_passes_query_and_three_images_directly_to_same_model(self):
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content='Direct answer')))
        factory = SimpleNamespace(get_model=lambda: model)
        llm = MentraLLM(factory)
        images = [dict(id=str(i), filename='photo.png', block=prepare_chat_image(raster())) for i in range(3)]
        result = asyncio.run(ChatService(llm).reply([('user', 'Compare these images')], image_context=images))
        self.assertEqual(result, 'Direct answer')
        payload = model.ainvoke.call_args.args[0][-1].content
        self.assertEqual(payload[0]['text'], 'Compare these images')
        self.assertEqual(sum(block['type'] == 'image_url' for block in payload), 3)

    def test_ocr_fallback_replaces_only_rejected_request_and_keeps_conversation_objects(self):
        async def scenario(status, error_type):
            rejected = error_type('Rejected', response=httpx.Response(status, request=httpx.Request('POST', 'https://test')), body=None)
            model = SimpleNamespace(ainvoke=AsyncMock(side_effect=[rejected, AIMessage(content='OCR answer')]))
            llm = MentraLLM(SimpleNamespace(get_model=lambda: model))
            user = HumanMessage(content=[dict(type='text', text='Read it'), prepare_chat_image(raster())])
            fallback = AsyncMock(side_effect=lambda prepared: setattr(prepared[-1], 'content', 'Read it\nOCR text'))
            token = chat_image_fallback.set(fallback)
            try:
                if status == 401:
                    with self.assertRaises(AuthenticationError):
                        await llm.ainvoke_messages(PromptSource.CHAT, [user])
                    fallback.assert_not_called()
                else:
                    result = await llm.ainvoke_messages(PromptSource.CHAT, [user])
                    self.assertEqual(result.content, 'OCR answer')
                    self.assertEqual(user.content, 'Read it\nOCR text')
                    self.assertEqual(model.ainvoke.call_count, 2)
                    fallback.assert_awaited_once()
            finally:
                chat_image_fallback.reset(token)
        asyncio.run(scenario(400, BadRequestError))
        asyncio.run(scenario(401, AuthenticationError))

    def test_orchestration_reuses_saved_images_only_on_explicit_followup_without_ocr(self):
        async def scenario():
            attachments = Mock()
            attachments.image_input.return_value = dict(id='saved', filename='photo.png', block=prepare_chat_image(raster()))
            chat = SimpleNamespace(reply=AsyncMock(return_value='Direct answer'))
            scope = dict(conversation_id='chat', attachment_ids=[], context_rows=[dict(role='user', content='Old query', metadata=dict(attachments=[dict(id='saved')]))],
                         history_references=[], memory_references=[])
            response = await OrchestrationService(chat, attachments=attachments).chat_reply(
                [('user', 'Explain the earlier image')], ChatSelection(), 'owner', history_scope=scope)
            self.assertEqual(response.content, 'Direct answer')
            attachments.image_input.assert_called_once_with('owner', 'saved', 'chat')
            attachments.extract.assert_not_called()
            self.assertEqual(chat.reply.call_args.kwargs['image_context'][0]['id'], 'saved')
            self.assertFalse(scope['execution_plan'].direct_candidate)
        asyncio.run(scenario())

    def test_unrelated_followup_does_not_resend_old_screenshot(self):
        async def scenario():
            attachments = Mock()
            chat = SimpleNamespace(reply=AsyncMock(return_value='Button with a title prop'))
            scope = dict(conversation_id='chat', attachment_ids=[], context_rows=[dict(role='user', content='Speed test', metadata=dict(attachments=[dict(id='speed',filename='speed.png')]))], history_references=[], memory_references=[])
            await OrchestrationService(chat, attachments=attachments).chat_reply(
                [('user', 'Make this React button take a title prop')], ChatSelection(), 'owner', history_scope=scope)
            attachments.image_input.assert_not_called()
            attachments.extract.assert_not_called()
            self.assertNotIn('image_context', chat.reply.call_args.kwargs)
            self.assertEqual(scope['assessment_attachment_ids'], [])
        asyncio.run(scenario())

    def test_attachment_selection_preserves_current_uploads_and_named_older_files(self):
        from app.langchain.attachment_selection import attachment_ids
        scope = dict(attachment_ids=[],current_user_message_id='now',context_rows=[
            dict(id='old',metadata=dict(attachments=[dict(id='first',filename='diagram.png')])),
            dict(id='newer',metadata=dict(attachments=[dict(id='second',filename='photo.png')])),
            dict(id='now',metadata={})])
        self.assertEqual(attachment_ids('Look at diagram.png again',scope), ['first'])
        self.assertEqual(attachment_ids('Compare diagram.png and photo.png',scope), ['second','first'])
        self.assertEqual(attachment_ids('Explain the image I uploaded',scope), ['second'])
        self.assertEqual(attachment_ids('Implement an image loading component',scope), [])
        scope['attachment_ids']=['current']
        self.assertEqual(attachment_ids('Compare these',scope), ['current'])
        scope['attachment_ids']=[]
        scope['context_rows'][-1]['metadata']={'attachments':[dict(id='current')]}
        self.assertEqual(attachment_ids('Compare these',scope), ['current'])

    def test_three_images_fit_the_default_tool_chat_budget(self):
        async def scenario():
            model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content='Direct answer')))
            model.bind_tools = lambda *args, **kwargs: model
            llm = MentraLLM(SimpleNamespace(get_model=lambda: model))
            images = [dict(id=str(i), filename='photo.png', block=prepare_chat_image(raster())) for i in range(3)]
            scope = dict(current_user_message_id='current', context_rows=[dict(id='current', role='user', content='Compare the diagrams')],
                history_references=[], memory_references=[], evidence_ids=set(), visible_ids=[], user_sequence=3)
            result = await ChatService(llm).reply([('user', 'Compare the diagrams')], image_context=images,
                history_runtime=(None, 'owner', scope))
            self.assertEqual(result, 'Direct answer')
            self.assertTrue(has_images(model.ainvoke.call_args.args[0]))
        asyncio.run(scenario())
