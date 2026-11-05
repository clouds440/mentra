import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.chat.schemas import SendTurn
from app.langchain.chat_service import ChatService
from app.langchain.llm import MentraLLM


class SourceAnnotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_the_selected_text_and_source_are_forwarded(self):
        turn = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=2,
            content='Explain this part.', source_annotations=[
                {'text': '  Selected sentence.  ', 'source': {'kind': 'chat', 'title': 'Mentra response'}},
                {'text': 'Publisher excerpt.', 'source': {'kind': 'web', 'title': 'Article', 'url': 'https://example.org/article'}},
            ])
        annotations = turn.model_dump(mode='json')['source_annotations']
        message_id = str(uuid4())
        rows = [dict(id=message_id, role='user', content=turn.content, metadata={'source_annotations': annotations})]
        scope = {'context_rows': rows, 'user_sequence': 3}
        reply = AsyncMock(return_value=AIMessage(content='Here is an explanation.'))
        with patch('app.langchain.history_orchestration.tool_reply', reply):
            service = ChatService(Mock(spec=MentraLLM))
            await service.reply([('user', turn.content)], history_runtime=(None, str(uuid4()), scope))

        model_context = reply.await_args.args[6]['user_source_excerpts']
        self.assertEqual(model_context['items'], [dict(message_id=message_id, **item) for item in annotations])
        self.assertEqual(annotations[0], {'text': 'Selected sentence.', 'source': {'kind': 'chat', 'title': 'Mentra response'}})
        self.assertIn('quoted evidence', model_context['instruction'])

    def test_annotations_are_bounded_and_chat_excerpts_do_not_store_a_message_link(self):
        base = dict(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=2, content='')
        source = {'kind': 'chat', 'title': 'Your message'}
        self.assertEqual(SendTurn(**base, source_annotations=[{'text': 'Excerpt', 'source': source}]).content, '')
        for annotation in ({'text': 'x' * 1601, 'source': source},
                {'text': 'Excerpt', 'source': dict(source, message_id=str(uuid4()))},
                {'text': 'Excerpt', 'source': {'kind': 'web', 'title': 'Private', 'url': 'https://127.0.0.1/'}}):
            with self.assertRaises(ValidationError):
                SendTurn(**base, source_annotations=[annotation])

    async def test_whole_page_supplies_readable_text_and_handles_unavailable_publishers(self):
        first = {'kind': 'web', 'title': 'Article', 'url': 'https://example.org/article'}
        second = {'kind': 'web', 'title': 'Blocked', 'url': 'https://example.org/blocked'}
        turn = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=2,
            content='Compare these sources.', source_annotations=[dict(mode='page', source=first), dict(mode='page', source=second)])
        annotations = turn.model_dump(mode='json')['source_annotations']
        message_id = str(uuid4())
        rows = [
            dict(id='old', role='user', content='Earlier', metadata={'source_annotations': [annotations[0]]}),
            dict(id=message_id, role='user', content=turn.content, metadata={'source_annotations': annotations}),
        ]
        scope = {'context_rows': rows, 'current_user_message_id': message_id, 'user_sequence': 3}
        reply = AsyncMock(return_value=AIMessage(content='Here is the comparison.'))
        reader = AsyncMock(side_effect=[{'url': first['url'], 'blocks': ['Article text. ' * 600]}, None])
        with patch('app.langchain.history_orchestration.tool_reply', reply), patch('app.workspace.source_context.read_publisher', reader):
            await ChatService(Mock(spec=MentraLLM)).reply([('user', turn.content)], history_runtime=(None, str(uuid4()), scope))
        items = reply.await_args.args[6]['user_source_excerpts']['items']
        self.assertEqual(reader.await_count, 2)
        self.assertEqual(items[0]['status'], 'readable')
        self.assertEqual(len(items[0]['text']), 3000)
        self.assertEqual(items[0]['resolved_url'], first['url'])
        self.assertTrue(items[0]['sample_limited'])
        self.assertEqual(items[1]['status'], 'unavailable')
        self.assertNotIn('text', items[1])
        self.assertNotIn('text', items[2])
        self.assertNotIn('text', annotations[0])
