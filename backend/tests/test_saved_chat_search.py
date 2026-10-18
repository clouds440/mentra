import os
import unittest
from uuid import uuid4
from sqlalchemy import select, update, text, event
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.history_reader import ChatReadFacade
from app.chat.repositories.tables import conversations, messages
from app.chat.schemas import SendTurn
from app.core.exceptions import AppError
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires dedicated database')
class SavedChatSearchTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox(); self.addCleanup(self.db.close)
        self.owner, self.other = learner_id('alice'), learner_id('bob')
        self.repo = ChatRepository(self.db.sessions); self.reader = ChatReadFacade(self.repo)

    def chat(self, content='Study force', answer='Saved explanation', owner=None, title=None):
        owner = owner or self.owner
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content=content)
        job = self.repo.begin_turn(owner, request)
        self.repo.finish(owner, job, dict(content=answer))
        page = self.repo.status(owner, str(request.conversation_id))
        if title: self.repo.edit(owner, str(request.conversation_id), page['conversation']['revision'], title)
        return page

    def test_literal_unicode_and_title_search_excludes_foreign_deleted_and_tool_rows(self):
        page = self.chat('اردو میں رفتار سمجھائیں', 'Literal 50%_value and an explanation.', title='Mechanics revision')
        self.chat('اردو میں رفتار سمجھائیں', owner=self.other)
        gone = self.chat('Deleted private phrase')
        self.repo.edit(self.owner, gone['conversation']['id'], gone['conversation']['revision'], None, True)
        for query in ('اردو','50%_value','MECHANICS REV'):
            hits = self.reader.search_saved(self.owner, query)
            self.assertEqual(len(hits.items), 1, hits)
            self.assertEqual(str(hits.items[0].conversation_id), page['conversation']['id'])
        self.assertEqual(self.reader.search_saved(self.owner, 'Deleted private').items, [])
        self.assertEqual(self.reader.search_saved(self.owner, "%' OR 1=1 --").items, [])
        self.assertEqual(self.reader.search_saved(self.owner, '   ').items, [])
        with self.assertRaises(AppError): self.reader.search_saved(self.owner, 'bad\x00query')

    def test_pagination_snippets_and_title_hits_are_bounded(self):
        page = self.chat('Shared needle', 'x'*600+' deep needle '+'y'*600, title='Needle title')
        with self.db.sessions.begin() as session:
            session.execute(messages.insert(), [dict(id=str(uuid4()),learner_id=self.owner,conversation_id=page['conversation']['id'],
                sequence=index+3,role='user',content='Shared needle '+str(index),metadata={},created_at=page['conversation']['created_at']) for index in range(44)])
            session.execute(update(conversations).where(conversations.c.id==page['conversation']['id']).values(message_count=46))
        pages = [self.reader.search_saved(self.owner, 'needle', offset) for offset in (0,20,40)]
        self.assertEqual([len(p.items) for p in pages], [20,20,6])
        ids = [str(x.matched_message_id) for p in pages for x in p.items]
        self.assertEqual(len(set(ids)),46)
        self.assertTrue(all(len(x.snippet)<=241 for p in pages for x in p.items))
        self.assertEqual(len(self.reader.search_saved(self.owner, 'Needle title').items), 1)

    def test_exact_window_reads_unloaded_message_and_reauthorizes_deletion_and_identity(self):
        page = self.chat('First searchable message', 'First reply')
        mid = page['items'][0]['id']; cid = page['conversation']['id']
        with self.db.sessions.begin() as session:
            session.execute(messages.insert(), [dict(id=str(uuid4()),learner_id=self.owner,conversation_id=cid, sequence=index+3,
                role='assistant' if index%2 else 'user',content='Later message '+str(index),metadata={},created_at=page['conversation']['created_at']) for index in range(120)])
            session.execute(update(conversations).where(conversations.c.id==cid).values(message_count=122))
        self.assertNotIn(mid, [m['id'] for m in self.repo.status(self.owner, cid)['items']])
        value = self.reader.saved_exchange(self.owner, cid, mid)
        self.assertEqual(str(value.matched_message_id), mid)
        self.assertEqual(value.messages[0].content, 'First searchable message')
        self.assertLessEqual(len(value.messages),3)
        for owner, chat in ((self.other,cid),(self.owner,str(uuid4()))):
            with self.assertRaises(AppError): self.reader.saved_exchange(owner, chat, mid)
        current = self.repo.status(self.owner,cid)
        self.repo.edit(self.owner,cid,current['conversation']['revision'],None,True)
        with self.assertRaises(AppError): self.reader.saved_exchange(self.owner,cid,mid)

    def test_selective_search_uses_existing_trigram_index_on_large_history(self):
        page = self.chat()
        with self.db.sessions.begin() as session:
            session.execute(text("""INSERT INTO chat_message (id,learner_id,conversation_id,sequence,role,content,metadata,created_at)
                SELECT gen_random_uuid(), :owner, :chat, n+2, 'user',
                    CASE WHEN n=5000 THEN 'selective-search-marker' ELSE repeat('ordinary study text ',8) END,
                    '{}'::jsonb, now() FROM generate_series(1,10000) n"""), {'owner':self.owner,'chat':page['conversation']['id']})
            # Bulk fixture loads leave a large GIN pending list; flush it as
            # maintenance would before comparing a steady-state selective plan.
            session.execute(text("SELECT pg_catalog.gin_clean_pending_list('idx_chat_history_trgm'::regclass)"))
            session.execute(text('ANALYZE chat_message'))
        captured = []
        def capture(connection,cursor,statement,parameters,context,many):
            if 'UNION ALL' in statement: captured.append((statement,parameters))
        event.listen(self.db.engine,'before_cursor_execute',capture)
        try: self.assertEqual(len(self.reader.search_saved(self.owner,'selective-search-marker').items),1)
        finally: event.remove(self.db.engine,'before_cursor_execute',capture)
        with self.db.engine.connect() as connection:
            plan = '\n'.join(row[0] for row in connection.exec_driver_sql('EXPLAIN (ANALYZE, BUFFERS) '+captured[0][0], captured[0][1]))
        self.assertIn('idx_chat_history_trgm',plan)

    def test_api_is_private_and_query_does_not_enter_diagnostic_capture(self):
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.conversations import router
        from app.student_profile.dependencies import require_onboarded_identity
        from app.core.observability.payloads import capture
        page = self.chat('Sensitive search phrase')
        app = FastAPI(); app.state.conversation_service = SimpleNamespace(repository=self.repo)
        app.include_router(router,prefix='/api/v1')
        app.dependency_overrides[require_onboarded_identity] = lambda: SimpleNamespace(learner_id=self.owner)
        with TestClient(app) as client:
            response = client.get('/api/v1/conversations/search',params={'query':'Sensitive search phrase'})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.headers['cache-control'],'no-store')
            mid = response.json()['items'][0]['matched_message_id']
            response = client.get(f"/api/v1/conversations/{page['conversation']['id']}/messages/{mid}/window")
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertNotIn('Sensitive search phrase',str(capture({'query':'Sensitive search phrase'})))
