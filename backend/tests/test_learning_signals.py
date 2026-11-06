import unittest
from uuid import uuid4
from unittest.mock import AsyncMock
from sqlalchemy import select,func,update,event
from pydantic import ValidationError
from app.core.config import Settings
from app.core.exceptions import AppError
from app.learner import LearnerEngine
from app.learner.signal_schemas import LearningSignal,LearningSignalExtraction
from app.learner.signals import admit_signals
from app.learner.schemas import LearnerContextPacket
from app.learner.repositories.tables import learning_evidence,concept,learner_concept_state
from app.learner.repositories.tables.signals import learning_signals
from app.langchain.evidence_worker import ChatEvidenceWorker
from app.langchain.repositories.evidence import ChatEvidenceRepository
from app.langchain.repositories.evidence_tables import jobs
from app.langchain.llm import MentraLLM
from app.langchain.signal_payloads import capture_windows
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.tables import messages
from app.chat.schemas import SendTurn
from testing.postgres import PostgresSandbox
from testing.history_model import HistoryChatFactory
from testing.identities import learner_id


class SignalContractTests(unittest.TestCase):
    def extract(self,**updates):
        return LearningSignalExtraction(signals=[LearningSignal(**dict(dict(kind='struggle',label='Chain rule',
            quote='أنا محتار في قاعدة السلسلة.',confidence=.95),**updates))],disposition='learning_signals')

    def test_exact_native_spans_new_labels_and_duplicate_source_are_preserved_without_scores(self):
        text='موضوع اليوم. أنا محتار في قاعدة السلسلة.'
        source=dict(id='user',kind='user',text=text,revision='hash')
        extracted=self.extract();extracted.signals.append(extracted.signals[0])
        values,rejected=admit_signals(extracted,[source],'',{},[])
        self.assertEqual(len(values),1);self.assertFalse(rejected)
        self.assertEqual(values[0]['span_start'],text.index('أنا'))
        self.assertIsNone(values[0]['concept_id'])
        self.assertEqual(values[0]['details']['scoring'],'not_admitted')
        self.assertNotIn('score',values[0]);self.assertNotIn('mastery',values[0])

    def test_missing_ambiguous_low_confidence_and_forged_source_cannot_be_admitted(self):
        source=dict(id='user',kind='user',text='أنا محتار في قاعدة السلسلة. أنا محتار في قاعدة السلسلة.',revision='hash')
        for updates in ({},{'start':3},{'source_id':'foreign'},{'confidence':.1}):
            self.assertFalse(admit_signals(self.extract(**updates),[source],'',{},[])[0])
        source['text']='أنا محتار في قاعدة السلسلة.'
        self.assertIsNone(admit_signals(self.extract(concept_id='foreign'),[source],'',{},[])[0][0]['concept_id'])
        with self.assertRaises(ValidationError):
            LearningSignal.model_validate(dict(kind='demonstration',label='Algebra',quote='x=2',confidence=1,score=1))

    def test_copied_assistant_answer_cannot_become_a_demonstration(self):
        quote='The net force is zero when velocity is constant.'
        source=dict(id='user',kind='user',text=quote,revision='hash')
        values,_=admit_signals(self.extract(kind='demonstration',quote=quote,authorship='student'),[source],quote,{},[])
        self.assertEqual(values[0]['kind'],'encounter')
        self.assertEqual(values[0]['details']['authorship'],'quoted')

    def test_unicode_window_budget_covers_the_complete_user_source(self):
        from types import SimpleNamespace
        llm=MentraLLM(SimpleNamespace(_settings=Settings(chat_context_window_tokens=8192)))
        text=('أريد فهم الاشتقاق وليس حفظ الإجابة. '*130)[:4000]
        source=dict(id='user',kind='user',text=text,revision='hash',coverage='complete')
        windows=list(capture_windows(llm,dict(sources=[source],question='Previous support. '*100),LearnerContextPacket()))
        covered=set()
        for _,payload in windows:
            window=payload['source'];start=window['offset']
            self.assertEqual(window['text'],text[start:start+len(window['text'])])
            covered.update(range(start,start+len(window['text'])))
        self.assertEqual(covered,set(range(len(text))))


class SignalCaptureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db=PostgresSandbox();self.addCleanup(self.db.close)
        self.owner,self.other=learner_id('alice'),learner_id('bob')
        self.chat=ChatRepository(self.db.sessions);self.repository=ChatEvidenceRepository(self.db.sessions)
        self.learner=LearnerEngine(self.db.repository);self.llm=MentraLLM(HistoryChatFactory())
        self.quote='أنا محتار في قاعدة السلسلة.';self.kind='struggle';self.offsets=[];self.fail_once=False
        async def infer(source,payload,**kwargs):
            self.assertEqual(self.db.engine.pool.checkedout(),0,'A DB session crossed a model wait')
            window=payload['source'];self.offsets.append(window['offset'])
            if self.fail_once and window['offset']>0:
                self.fail_once=False;raise RuntimeError('provider interrupted')
            observations=[dict(kind=self.kind,label='Chain rule',topic='Differentiation',source_id=window['id'],
                quote=self.quote,confidence=.95,authorship='student')] if self.quote in window['text'] else []
            return LearningSignalExtraction(signals=observations,disposition='learning_signals' if observations else 'non_learning')
        self.llm.ainvoke=AsyncMock(side_effect=infer)
        self.worker=ChatEvidenceWorker(self.repository,self.llm,self.learner)

    def turn(self,text=None,*,reply=None,conversation=None,attachments=()):
        existing=conversation is not None
        conversation=conversation or str(uuid4())
        revision=self.chat.status(self.owner,conversation)['conversation']['revision'] if existing else 0
        job=self.chat.begin_turn(self.owner,SendTurn(conversation_id=conversation,client_turn_id=uuid4(),expected_revision=revision,
            content=self.quote if text is None else text,attachment_ids=list(attachments)))
        self.chat.finish(self.owner,job,response=reply or dict(content='Let us work through the chain rule.'))
        return job

    async def test_cold_unknown_arabic_struggle_is_captured_without_a_question_or_registry(self):
        job=self.turn()
        self.assertTrue(await self.worker.run_once())
        self.assertEqual(self.llm.ainvoke.await_count,1)
        page=self.learner.get_learning_signals(self.owner)
        self.assertEqual(len(page['items']),1)
        self.assertEqual(page['items'][0]['quote'],self.quote)
        self.assertIsNone(page['items'][0]['concept_id'])
        with self.db.sessions() as session:
            for table in (concept,learning_evidence,learner_concept_state):
                self.assertEqual(session.scalar(select(func.count()).select_from(table)),0)
            self.assertEqual(session.scalar(select(jobs.c.disposition).where(jobs.c.turn_id==job['turn_id'])),'captured')

    async def test_even_a_high_confidence_demonstration_does_not_write_chat_mastery(self):
        self.kind='demonstration';self.quote='The net force is zero because the velocity is constant.'
        self.turn();await self.worker.run_once()
        self.assertEqual(self.learner.get_learning_signals(self.owner)['items'][0]['kind'],'demonstration')
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),0)
            self.assertEqual(session.scalar(select(func.count()).select_from(learner_concept_state)),0)

    async def test_uncertain_inference_is_preserved_pending_without_personalization_admission(self):
        self.llm.ainvoke=AsyncMock(return_value=LearningSignalExtraction(signals=[dict(kind='demonstration',
            label='Chain rule',quote=self.quote,confidence=.5)],disposition='learning_signals'))
        job=self.turn();await self.worker.run_once()
        self.assertEqual(self.learner.get_learning_signals(self.owner)['items'],[])
        pending=self.learner.get_learning_signals(self.owner,status='pending')['items']
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]['quote'],self.quote)
        self.assertEqual(pending[0]['details']['classification'],'pending_review')
        self.assertEqual(self.learner.get_learning_signals(self.other,status='all')['items'],[])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(jobs.c.disposition).where(jobs.c.turn_id==job['turn_id'])),'captured_pending_review')
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),0)

    async def test_unique_exact_quote_repairs_model_offset_without_modifying_source_words(self):
        self.llm.ainvoke=AsyncMock(return_value=LearningSignalExtraction(signals=[dict(kind='struggle',
            label='Chain rule',quote=self.quote,start=7,end=8,confidence=.95)],disposition='learning_signals'))
        self.turn();await self.worker.run_once()
        item=self.learner.get_learning_signals(self.owner)['items'][0]
        self.assertEqual((item['span_start'],item['span_end']),(0,len(self.quote)))
        self.assertEqual(item['quote'],self.quote)

    async def test_long_spontaneous_work_is_windowed_and_retry_reuses_completed_windows(self):
        text=('Additional working. '*220)[:3700]+self.quote
        job=self.turn(text);self.fail_once=True
        self.assertTrue(await self.worker.run_once())
        with self.db.sessions() as session:
            saved=session.execute(select(jobs).where(jobs.c.turn_id==job['turn_id'])).mappings().one()
        self.assertEqual(saved['state'],'failed');self.assertTrue(saved['progress']['windows'])
        self.learner.retry_learning_signal_capture(self.owner,job['turn_id'])
        self.assertTrue(await self.worker.run_once())
        self.assertEqual(self.offsets.count(0),1)
        self.assertEqual(len(self.learner.get_learning_signals(self.owner)['items']),1)

    async def test_source_change_and_duplicate_completion_are_fenced(self):
        self.turn();job=self.repository.claim()
        extraction=LearningSignalExtraction(signals=[dict(kind='struggle',label='Chain rule',quote=self.quote,confidence=.95)])
        accepted,rejected=admit_signals(extraction,job['sources'],'',{},[])
        self.repository.complete_signals(job,accepted,'captured',rejected)
        self.repository.complete_signals(job,accepted,'captured',rejected)
        self.assertEqual(len(self.learner.get_learning_signals(self.owner)['items']),1)
        changed=self.turn();claim=self.repository.claim()
        with self.db.sessions.begin() as session:
            session.execute(update(messages).where(messages.c.id==claim['user']['id']).values(content='Changed source'))
        with self.assertRaises(AppError): self.repository.complete_signals(claim,[],'non_learning',{})

    async def test_formal_review_has_a_terminal_reason_without_a_second_mastery_path(self):
        self.turn('My numbered answers.',reply=dict(content='Review complete.',response_outcome=dict(state='completed',
            tasks=[dict(id='grade',operation='assessment_answer',state='completed')])))
        self.assertTrue(await self.worker.run_once())
        self.llm.ainvoke.assert_not_awaited()
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(jobs.c.disposition)),'formal_assessment_managed')

    async def test_withdraw_and_retry_are_owner_scoped_and_do_not_delete_source(self):
        job=self.turn();await self.worker.run_once()
        signal=self.learner.get_learning_signals(self.owner)['items'][0]
        self.assertEqual(self.learner.get_learning_signals(self.other)['items'],[])
        with self.assertRaises(AppError): self.learner.withdraw_learning_signal(self.other,str(signal['id']))
        with self.assertRaises(AppError): self.learner.retry_learning_signal_capture(self.other,job['turn_id'])
        self.learner.withdraw_learning_signal(self.owner,str(signal['id']))
        self.assertEqual(self.learner.get_learning_signals(self.owner)['items'],[])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_signals)),1)

    async def test_enqueue_is_one_statement_and_no_classifier_runs_before_commit(self):
        statements=[]
        def inspect(connection,cursor,statement,*args):
            if 'chat_evidence_job' in statement: statements.append(statement)
        event.listen(self.db.engine,'before_cursor_execute',inspect)
        try: self.turn()
        finally: event.remove(self.db.engine,'before_cursor_execute',inspect)
        self.assertEqual(len(statements),1)
        self.llm.ainvoke.assert_not_awaited()

    async def test_question_mark_and_english_help_prefix_are_not_capture_requirements(self):
        first=self.turn('Teach me calculus.',reply=dict(content='أخبرني بما يصعب عليك في الاشتقاق'))
        self.repository.complete(self.repository.claim(),lambda tx:None,disposition='non_learning')
        self.turn('Help please. '+self.quote,conversation=first['conversation_id'])
        await self.worker.run_once()
        self.assertEqual(len(self.learner.get_learning_signals(self.owner)['items']),1)

    async def test_native_attachment_text_is_captured_with_extraction_provenance(self):
        from io import BytesIO
        from testing.files import create_test_files
        from app.chat.repositories.attachments import AttachmentRepository
        files=create_test_files(self.db.sessions)
        attachment_repository=AttachmentRepository(self.db.sessions,files)
        stored=files.upload(self.owner,BytesIO(self.quote.encode()),'working.txt','chat','capture-source')
        attachment=attachment_repository.create(self.owner,'working.txt',stored)
        job=self.turn('Please inspect my working.',attachments=[attachment['id']])
        attachment_repository.save_extraction(self.owner,attachment['id'],job['conversation_id'],
            dict(blocks=[dict(text=self.quote,method='native')],reader_revision='native-test-v1',warnings=[]))
        await self.worker.run_once()
        signal=self.learner.get_learning_signals(self.owner)['items'][0]
        self.assertEqual(signal['source_kind'],'attachment')
        self.assertTrue(signal['source_revision'].startswith('native-test-v1:'))
        self.assertEqual(signal['details']['scoring'],'not_admitted')

    async def test_unread_attachment_has_an_explicit_terminal_disposition(self):
        from io import BytesIO
        from testing.files import create_test_files
        from app.chat.repositories.attachments import AttachmentRepository
        files=create_test_files(self.db.sessions)
        stored=files.upload(self.owner,BytesIO(b'not read'),'working.txt','chat','unread-capture-source')
        attachment=AttachmentRepository(self.db.sessions,files).create(self.owner,'working.txt',stored)
        job=self.turn('Please inspect this file.',attachments=[attachment['id']])
        await self.worker.run_once()
        with self.db.sessions() as session:
            row=session.execute(select(jobs).where(jobs.c.turn_id==job['turn_id'])).mappings().one()
        self.assertEqual(row['disposition'],'attachment_text_unavailable')
        self.assertEqual(row['receipt']['unavailable_attachments'],1)
        attachment_repository=AttachmentRepository(self.db.sessions,files)
        attachment_repository.save_extraction(self.owner,attachment['id'],job['conversation_id'],
            dict(blocks=[dict(text=self.quote,method='native')],reader_revision='native-ready-v1',warnings=[]))
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(jobs.c.state).where(jobs.c.turn_id==job['turn_id'])),'queued')
        await self.worker.run_once()
        self.assertEqual(len(self.learner.get_learning_signals(self.owner)['items']),1)
        self.assertEqual(self.llm.ainvoke.await_count,2,'Unchanged user text must not be classified again')

    async def test_attachment_source_refresh_preserves_user_signals_and_supersedes_old_extraction(self):
        from io import BytesIO
        from testing.files import create_test_files
        from app.chat.repositories.attachments import AttachmentRepository
        files=create_test_files(self.db.sessions);repository=AttachmentRepository(self.db.sessions,files)
        stored=files.upload(self.owner,BytesIO(self.quote.encode()),'working.txt','chat','refresh-capture-source')
        attachment=repository.create(self.owner,'working.txt',stored)
        job=self.turn(attachments=[attachment['id']]);await self.worker.run_once()
        original_user=self.learner.get_learning_signals(self.owner)['items'][0]
        extraction=dict(blocks=[dict(text=self.quote,method='native')],reader_revision='native-ready-v1',warnings=[])
        repository.save_extraction(self.owner,attachment['id'],job['conversation_id'],extraction)
        await self.worker.run_once()
        self.assertEqual(self.llm.ainvoke.await_count,2)
        repository.save_extraction(self.owner,attachment['id'],job['conversation_id'],extraction)
        self.assertFalse(await self.worker.run_once(),'Identical extraction must not requeue capture')
        self.quote='أنا لا أفهم الاشتقاق الضمني.'
        repository.save_extraction(self.owner,attachment['id'],job['conversation_id'],dict(
            blocks=[dict(text=self.quote,method='native')],reader_revision='native-ready-v2',warnings=[]))
        await self.worker.run_once()
        items=self.learner.get_learning_signals(self.owner)['items']
        self.assertEqual(len(items),2)
        self.assertIn(original_user['id'],[item['id'] for item in items])
        self.assertEqual([item['quote'] for item in items if item['source_kind']=='attachment'],[self.quote])
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_signals)),3)

    async def test_capture_api_keeps_sources_owned_and_supports_withdrawal(self):
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.learning import router
        from app.student_profile.dependencies import require_onboarded_identity
        from app.core.exception_handlers import register_exception_handlers
        job=self.turn();await self.worker.run_once()
        app=FastAPI();app.state.learner_service=self.learner;register_exception_handlers(app);app.include_router(router)
        owner=[self.other]
        app.dependency_overrides[require_onboarded_identity]=lambda:SimpleNamespace(learner_id=owner[0])
        client=TestClient(app)
        self.assertEqual(client.get('/learning/signals').json()['items'],[])
        self.assertEqual(client.post(f'/learning/signal-captures/{job["turn_id"]}/retry').status_code,404)
        owner[0]=self.owner
        response=client.get('/learning/signals')
        self.assertEqual(response.headers['cache-control'],'no-store')
        identifier=response.json()['items'][0]['id']
        self.assertEqual(client.delete(f'/learning/signals/{identifier}').status_code,204)
        self.assertEqual(client.get('/learning/signals').json()['items'],[])
