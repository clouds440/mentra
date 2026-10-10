import asyncio
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, func
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.migrate import migration_config, upgrade
from app.db.metadata import metadata
from app.chat.repositories.postgres import ChatRepository, now
from app.chat.repositories.history_reader import ChatReadFacade
from app.chat.schemas import SendTurn
from app.chat.service import ConversationService
from app.history_management.repositories.postgres import MemoryRepository
from app.history_management.repositories.tables import memories, evidence, revisions, receipts
from app.history_management.schemas import MemoryEdit, MemoryToolInput, HistoryLookup, PreferencesEdit
from app.history_management.memory.validation import MemoryValidator, Admission
from app.history_management.service import HistoryManagement
from app.history_management.budgets import ToolBudget
from app.langchain.chat_service import ChatService
from app.core.exceptions import AppError
from langchain_core.messages import AIMessage, ToolMessage
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class Verifier:
    calls = 0
    def __init__(self, **changes):
        self.changes = changes
    async def ainvoke(self, *args, **kwargs):
        self.calls += 1
        return Admission(**dict(supported=True, explicit_user_statement=self.changes.get('explicit', True),
            sensitive=self.changes.get('sensitive', False), explicit_remember_request=self.changes.get('consent', False),
            durable=True, contradicts_existing=self.changes.get('conflict', False)))


class HistoryManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PostgresSandbox()
        cls.owner, cls.other = learner_id('alice'), learner_id('bob')
        cls.chat = ChatRepository(cls.db.sessions)
        cls.reader = ChatReadFacade(cls.chat)
        cls.repo = MemoryRepository(cls.db.sessions)
    @classmethod
    def tearDownClass(cls):
        cls.db.close()
    def question(self, content=None, owner=None):
        owner = owner or self.owner
        body = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content=content or 'I prefer diagrams ' + uuid4().hex)
        job = self.chat.begin_turn(owner, body)
        row = self.chat.context_rows(owner, job['conversation_id'], job['user_sequence'])[-1]
        scope = dict(job, current_user_message_id=row['id'], evidence_ids={row['id']}, visible_ids=[], visible_user_messages=[],
            context_rows=[row], history_references=[], memory_references=[])
        return row, scope
    def manual(self, text=None):
        return self.repo.write(self.owner, text or 'Manual preference '+uuid4().hex, 'preference', str(uuid4()))['memory']
    def propose(self, row, scope, verifier=None, content=None):
        verifier = verifier or Verifier()
        service = HistoryManagement(self.repo, self.reader, MemoryValidator(verifier))
        body = MemoryToolInput(action='remember', content=content or row['content'], category='preference', evidence_message_id=row['id'], evidence_quote=row['content'])
        return asyncio.run(service.memory(self.owner, scope, body, ToolBudget()))
    def test_manual_crud_revision_evidence_and_owner_isolation(self):
        memory = self.manual()
        for action in [lambda: self.repo.detail(self.other, memory['id']), lambda: self.repo.edit(self.other, memory['id'], MemoryEdit(expected_revision=1, content='stolen')), lambda: self.repo.remove(self.other, memory['id'], 1)]:
            with self.assertRaises(AppError): action()
        updated = self.repo.edit(self.owner, memory['id'], MemoryEdit(expected_revision=1, content='Updated '+uuid4().hex))
        self.assertEqual(updated['revision'], 2)
        with self.assertRaises(AppError): self.repo.edit(self.owner, memory['id'], MemoryEdit(expected_revision=1, pinned=True))
        self.assertEqual(self.repo.detail(self.owner, memory['id'])['evidence'][0]['quote'], updated['content'])
        self.repo.remove(self.owner, memory['id'], 2)
        with self.db.sessions() as session:
            for table, column in [(memories, memories.c.id), (evidence, evidence.c.memory_id), (revisions, revisions.c.memory_id)]:
                self.assertEqual(session.scalar(select(func.count()).select_from(table).where(column == memory['id'])), 0)
    def test_idempotent_create_and_changed_payload_rejected(self):
        key = str(uuid4()); text = 'Durable '+uuid4().hex
        first = self.repo.write(self.owner, text, 'fact', key)
        self.assertEqual(self.repo.write(self.owner, text, 'fact', key)['memory']['id'], first['memory']['id'])
        with self.assertRaises(AppError): self.repo.write(self.owner, 'different', 'fact', key)
    def test_competing_manual_updates_only_one_commits(self):
        memory = self.manual()
        def edit(value):
            try: return self.repo.edit(self.owner, memory['id'], MemoryEdit(expected_revision=1, content=value))['revision']
            except AppError: return 'conflict'
        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(edit, ['One '+uuid4().hex, 'Two '+uuid4().hex]))
        self.assertEqual(outcomes.count(2), 1); self.assertEqual(outcomes.count('conflict'), 1)
    def test_active_memory_survives_chat_deletion(self):
        row, scope = self.question()
        result = self.propose(row, scope)
        self.assertEqual(result['outcome'], 'saved')
        self.chat.edit(self.owner, scope['conversation_id'], 2, remove=True)
        saved = self.repo.detail(self.owner, result['memory']['id'])
        self.assertTrue(saved['evidence'][0]['source_deleted'])
        self.assertEqual(saved['evidence'][0]['quote'], row['content'])
    def test_pending_inference_removed_with_only_source_chat(self):
        row, scope = self.question()
        result = self.propose(row, scope, Verifier(explicit=False))
        self.assertEqual(result['outcome'], 'pending')
        self.chat.edit(self.owner, scope['conversation_id'], 2, remove=True)
        with self.assertRaises(AppError): self.repo.detail(self.owner, result['memory']['id'])
    def test_user_pinned_candidate_survives_source_deletion_without_becoming_fact(self):
        row, scope = self.question()
        result = self.propose(row, scope, Verifier(explicit=False))
        memory_id = result['memory']['id']
        self.repo.edit(self.owner, memory_id, MemoryEdit(expected_revision=1, pinned=True))
        self.chat.edit(self.owner, scope['conversation_id'], 2, remove=True)
        retained = self.repo.detail(self.owner, memory_id)
        self.assertTrue(retained['pinned']); self.assertEqual(retained['status'], 'pending')
        self.assertTrue(retained['evidence'][0]['source_deleted'])
    def test_new_explicit_support_keeps_inference_pending_and_retains_other_source(self):
        content = 'I prefer evidence diagrams '+uuid4().hex
        row, scope = self.question(content)
        result = self.propose(row, scope, Verifier(explicit=False))
        other_row, other_scope = self.question(content)
        strengthened = self.propose(other_row, other_scope)
        self.assertEqual(strengthened['memory']['status'], 'pending')
        self.assertEqual(len(self.repo.detail(self.owner, result['memory']['id'])['evidence']), 2)
        self.chat.edit(self.owner, scope['conversation_id'], 2, remove=True)
        self.assertEqual(self.repo.detail(self.owner, result['memory']['id'])['status'], 'pending')
    def test_manual_confirmation_and_expired_memory_excluded(self):
        row, scope = self.question()
        result = self.propose(row, scope, Verifier(explicit=False))
        mid = result['memory']['id']
        self.assertFalse(any(x['id'] == mid for x in self.repo.list(self.owner, row['content'], recall=True)['items']))
        self.repo.edit(self.owner, mid, MemoryEdit(expected_revision=1, confirm=True, expires_at=now()-timedelta(days=1)))
        self.assertFalse(any(x['id'] == mid for x in self.repo.list(self.owner, row['content'], recall=True)['items']))
        self.repo.edit(self.owner, mid, MemoryEdit(expected_revision=2, confirm=True, clear_expiration=True))
        self.assertTrue(any(x['id'] == mid for x in self.repo.list(self.owner, row['content'], recall=True)['items']))
    def test_forget_suppresses_same_evidence_even_reworded(self):
        row, scope = self.question()
        result = self.propose(row, scope)
        self.repo.remove(self.owner, result['memory']['id'], 1)
        repeated = self.propose(row, scope, content='Reworded '+row['content'])
        self.assertEqual(repeated['outcome'], 'rejected')
    def test_retry_does_not_reverify_or_duplicate(self):
        row, scope = self.question()
        verifier = Verifier()
        first = self.propose(row, scope, verifier)
        repeated = self.propose(row, scope, verifier)
        self.assertEqual(first['memory']['id'], repeated['memory']['id'])
        self.assertEqual(verifier.calls, 1)

    def test_retry_cannot_claim_old_save_after_manual_correction(self):
        row, scope = self.question()
        saved = self.propose(row, scope)['memory']
        corrected = self.repo.edit(self.owner, saved['id'], MemoryEdit(expected_revision=saved['revision'], content='User corrected this '+uuid4().hex))
        scope['memory_references'] = []
        repeated = self.propose(row, scope)
        self.assertEqual(repeated['outcome'], 'rejected')
        self.assertFalse(scope['memory_references'])
        self.assertEqual(self.repo.detail(self.owner, saved['id'])['content'], corrected['content'])
    def test_sensitive_information_requires_specific_consent(self):
        row, scope = self.question('My medical diagnosis is private '+uuid4().hex)
        self.assertEqual(self.propose(row, scope, Verifier(sensitive=True))['outcome'], 'rejected')
        row, scope = self.question('Remember my medical diagnosis '+uuid4().hex)
        self.assertEqual(self.propose(row, scope, Verifier(sensitive=True, consent=True))['outcome'], 'saved')
    def test_secret_and_fabricated_evidence_rejected(self):
        row, scope = self.question('My password is not memory material')
        self.assertEqual(self.propose(row, scope)['outcome'], 'rejected')
        validator = MemoryValidator(Verifier())
        self.assertEqual(asyncio.run(validator.validate('I prefer diagrams', 'not in message', 'hello'))['outcome'], 'rejected')
        with self.assertRaises(AppError): self.manual('My API key is secret')
    def test_invisible_and_other_owner_evidence_rejected(self):
        row, scope = self.question(owner=self.other)
        scope['evidence_ids'] = set()
        self.assertEqual(self.propose(row, scope)['outcome'], 'rejected')
    def test_disable_and_turn_fencing(self):
        prefs = self.repo.preferences(self.owner)
        self.repo.set_preferences(self.owner, PreferencesEdit(automatic_memory=False, expected_revision=prefs['revision']))
        row, scope = self.question()
        self.assertEqual(self.propose(row, scope)['outcome'], 'rejected')
        prefs = self.repo.preferences(self.owner)
        self.repo.set_preferences(self.owner, PreferencesEdit(automatic_memory=True, expected_revision=prefs['revision']))
        self.chat.finish(self.owner, scope, dict(content='done'))
        with self.assertRaises(AppError): self.propose(row, scope)

    def test_disable_during_validation_blocks_commit_and_keeps_manual_and_recall(self):
        repo, owner = self.repo, self.owner
        class DisableDuringValidation(Verifier):
            async def ainvoke(self, *args, **kwargs):
                prefs = repo.preferences(owner)
                repo.set_preferences(owner, PreferencesEdit(automatic_memory=False, expected_revision=prefs['revision']))
                return await super().ainvoke(*args, **kwargs)
        row, scope = self.question()
        try:
            result = self.propose(row, scope, DisableDuringValidation())
            self.assertEqual(result['outcome'], 'rejected')
            self.assertFalse(self.repo.list(self.owner, row['content'])['items'])
            manual = self.manual('Disabled mode manual '+uuid4().hex)
            self.assertTrue(any(x['id'] == manual['id'] for x in self.repo.list(self.owner, manual['content'], recall=True)['items']))
        finally:
            prefs = repo.preferences(owner)
            repo.set_preferences(owner, PreferencesEdit(automatic_memory=True, expected_revision=prefs['revision']))

    def test_manual_duplicate_confirms_candidate_and_refreshes_expired_memory(self):
        row, scope = self.question()
        candidate = self.propose(row, scope, Verifier(explicit=False))['memory']
        confirmed = self.repo.write(self.owner, row['content'], 'preference', str(uuid4()))['memory']
        self.assertEqual(confirmed['id'], candidate['id'])
        self.assertEqual(confirmed['status'], 'active')
        self.assertEqual(confirmed['origin'], 'manual')
        self.repo.edit(self.owner, confirmed['id'], MemoryEdit(expected_revision=confirmed['revision'], expires_at=now()-timedelta(days=1)))
        refreshed = self.repo.write(self.owner, row['content'], 'preference', str(uuid4()))['memory']
        self.assertFalse(refreshed['stale'])
        self.assertIsNone(refreshed['expires_at'])
        self.repo.remove(self.owner, refreshed['id'], refreshed['revision'])
        self.assertEqual(self.propose(row, scope, content='Reworded '+row['content'])['outcome'], 'rejected')

    def test_manual_correction_retires_old_sources_and_refreshes_applicability(self):
        row, scope = self.question()
        saved = self.propose(row, scope)['memory']
        self.repo.edit(self.owner, saved['id'], MemoryEdit(expected_revision=saved['revision'], expires_at=now()-timedelta(days=1)))
        corrected = self.repo.edit(self.owner, saved['id'], MemoryEdit(expected_revision=saved['revision']+1, content='Corrected preference '+uuid4().hex))
        self.assertFalse(corrected['stale'])
        self.assertEqual(self.propose(row, scope, content='Old fact reworded '+row['content'])['outcome'], 'rejected')

    def test_conflict_review_uses_current_predecessor_revisions(self):
        original = self.manual()
        candidate = self.repo.write(self.owner, 'Conflicting '+uuid4().hex, 'fact', str(uuid4()), origin='ai', status='conflict', conflict_ids=[original['id']])['memory']
        updated = self.repo.edit(self.owner, original['id'], MemoryEdit(expected_revision=original['revision'], pinned=True))
        with self.assertRaises(AppError):
            self.repo.edit(self.owner, candidate['id'], MemoryEdit(expected_revision=candidate['revision'], confirm=True, resolve_conflict=True, conflict_revisions={original['id']: original['revision']}))
        detail = self.repo.detail(self.owner, candidate['id'])
        self.assertEqual(detail['conflicts'][0]['revision'], updated['revision'])
        resolved = self.repo.edit(self.owner, candidate['id'], MemoryEdit(expected_revision=candidate['revision'], confirm=True, resolve_conflict=True, conflict_revisions={original['id']: updated['revision']}))
        self.assertEqual(resolved['status'], 'active')
        self.assertEqual(self.repo.detail(self.owner, original['id'])['status'], 'conflict')

    def test_expired_ai_admission_and_ambiguous_edit_arguments_rejected(self):
        class PastDeadline(Verifier):
            async def ainvoke(self, *args, **kwargs):
                result = await super().ainvoke(*args, **kwargs)
                result.valid_until = now()-timedelta(days=1)
                return result
        row, scope = self.question()
        self.assertEqual(self.propose(row, scope, PastDeadline())['outcome'], 'rejected')
        self.assertFalse(self.repo.list(self.owner, row['content'])['items'])
        with self.assertRaises(ValueError): MemoryEdit(expected_revision=1, clear_expiration=True, expires_at=now())

    def test_historical_evidence_does_not_reset_freshness_and_new_statement_can_reaffirm(self):
        from app.chat.repositories.tables import messages
        row, scope = self.question()
        with self.db.sessions.begin() as session:
            session.execute(messages.update().where(messages.c.id == row['id']).values(created_at=now()-timedelta(days=400)))
        self.assertEqual(self.propose(row, scope)['outcome'], 'rejected')
        self.assertFalse(self.repo.list(self.owner, row['content'])['items'])
        first_row, first_scope = self.question()
        saved = self.propose(first_row, first_scope)['memory']
        with self.db.sessions.begin() as session:
            session.execute(memories.update().where(memories.c.id == saved['id']).values(expires_at=now()-timedelta(days=1)))
        second_row, second_scope = self.question(first_row['content'])
        reaffirmed = self.propose(second_row, second_scope)
        self.assertEqual(reaffirmed['outcome'], 'already_known')
        self.assertFalse(self.repo.detail(self.owner, saved['id'])['stale'])
        self.assertEqual(len(second_scope['memory_references']), 1)
    def test_history_keywords_fuzzy_windows_and_owner_isolation(self):
        keyword = 'hippopotamus'+uuid4().hex[:4]
        row, scope = self.question('I researched '+keyword)
        self.chat.finish(self.owner, scope, dict(content='An answer about '+keyword))
        current, active = self.question('Recall my earlier animal research')
        body = HistoryLookup(scope='all_chats', query=keyword)
        windows = self.reader.lookup(self.owner, active['conversation_id'], 1, body)
        self.assertTrue(windows); self.assertEqual([x['role'] for x in windows[0]['messages']], ['user','assistant'])
        self.assertFalse(self.reader.lookup(self.other, active['conversation_id'], 1, body))
        with self.assertRaises(ValueError): HistoryLookup(scope='all_chats')
        fuzzy = self.reader.lookup(self.owner, active['conversation_id'], 1, HistoryLookup(scope='all_chats', query=keyword[:-2]))
        self.assertTrue(fuzzy)
        self.chat.edit(self.owner, scope['conversation_id'], 3, remove=True)
        self.assertFalse(self.reader.lookup(self.owner, active['conversation_id'], 1, body))
    def test_failed_question_is_retrievable_and_visible_rows_excluded(self):
        row, scope = self.question('failedkeyword '+uuid4().hex)
        self.chat.finish(self.owner, scope, error='provider failed')
        windows = self.reader.lookup(self.owner, scope['conversation_id'], 2, HistoryLookup(query='failedkeyword'))
        self.assertTrue(windows)
        self.assertEqual(windows[0]['messages'][0]['exchange_status'], 'FAILED')
        self.assertFalse(self.reader.lookup(self.owner, scope['conversation_id'], 2, HistoryLookup(query='failedkeyword'), [row['id']]))
    def test_capacity_is_explicit_and_preserves_manual_records(self):
        bounded = MemoryRepository(self.db.sessions, active_limit=1, pending_limit=1)
        row, scope = self.question()
        service = HistoryManagement(bounded, self.reader, MemoryValidator(Verifier()))
        result = asyncio.run(service.memory(self.owner, scope, MemoryToolInput(action='remember', content=row['content'], evidence_quote=row['content'], evidence_message_id=row['id']), ToolBudget()))
        self.assertEqual(result['outcome'], 'rejected')
        self.assertTrue(self.manual()['id'])
    def test_final_publication_fences_deleted_memory(self):
        memory = self.manual()
        row, scope = self.question()
        self.repo.remove(self.owner, memory['id'], 1)
        self.chat.finish(self.owner, scope, dict(content='Old secret fact', memory_references=[dict(memory_id=memory['id'], revision=1, token='M1')]))
        answer = self.chat.history(self.owner, scope['conversation_id'])['items'][-1]
        self.assertNotIn('Old secret fact', answer['content'])
    def test_migration_drift(self):
        with self.db.engine.connect() as connection:
            changes = compare_metadata(MigrationContext.configure(connection), metadata)
            self.assertEqual(changes, [])
    def test_conflict_resolution_is_atomic_and_forget_purges_snapshots(self):
        first = self.manual('I prefer short explanations '+uuid4().hex)
        candidate = self.repo.write(self.owner, 'I now prefer longer explanations '+uuid4().hex, 'preference', str(uuid4()),
            origin='ai', status='conflict', conflict_ids=[first['id']])['memory']
        with self.assertRaises(AppError): self.repo.edit(self.owner, candidate['id'], MemoryEdit(expected_revision=1, confirm=True))
        self.repo.edit(self.owner, candidate['id'], MemoryEdit(expected_revision=1, confirm=True, resolve_conflict=True))
        self.assertEqual(self.repo.detail(self.owner, first['id'])['status'], 'conflict')
        self.assertEqual(self.repo.detail(self.owner, candidate['id'])['status'], 'active')
        self.repo.remove(self.owner, candidate['id'], 2)
        self.assertEqual(self.repo.detail(self.owner, first['id'])['conflicts'], [])
    def test_related_candidates_do_not_require_new_value_to_match_old_fact(self):
        first = self.manual('My favorite color is magenta '+uuid4().hex)
        related = self.repo.related(self.owner, 'My favorite color is indigo')
        self.assertIn(first['id'], [x['id'] for x in related])
    def test_conflict_resolution_cannot_overwrite_concurrent_manual_edit(self):
        first = self.manual()
        candidate = self.repo.write(self.owner, 'Correction '+uuid4().hex, 'fact', str(uuid4()), origin='ai', status='conflict', conflict_ids=[first['id']])['memory']
        self.repo.edit(self.owner, first['id'], MemoryEdit(expected_revision=1, pinned=True))
        with self.assertRaises(AppError): self.repo.edit(self.owner, candidate['id'], MemoryEdit(expected_revision=1, confirm=True, resolve_conflict=True))
        self.assertEqual(self.repo.detail(self.owner, first['id'])['status'], 'active')
        self.assertEqual(self.repo.detail(self.owner, candidate['id'])['status'], 'conflict')
    def test_keyset_pagination_and_literal_wildcard_search(self):
        key = 'pagination_'+uuid4().hex
        ids = {self.manual(key+' '+str(index))['id'] for index in range(7)}
        page = self.repo.list(self.owner, key, limit=3)
        collected = [x['id'] for x in page['items']]
        while page['next_cursor']:
            page = self.repo.list(self.owner, key, cursor=page['next_cursor'], limit=3)
            collected.extend(x['id'] for x in page['items'])
        self.assertEqual(set(collected), ids); self.assertEqual(len(collected), 7)
        self.assertFalse(self.repo.list(self.owner, query='%not_a_pattern%')['items'])
        with self.assertRaises(AppError): self.repo.list(self.owner, cursor='bad cursor')
    def test_validation_outage_and_unsupported_claim_do_not_persist(self):
        class Unavailable:
            async def ainvoke(self, *args, **kwargs): raise RuntimeError('provider unavailable')
        row, scope = self.question()
        self.assertEqual(self.propose(row, scope, Unavailable())['outcome'], 'unavailable')
        self.assertFalse(self.repo.list(self.owner, row['content'])['items'])
    def test_manual_ai_revision_race_preserves_user_authority(self):
        memory = self.manual()
        row, scope = self.question()
        outcome = self.repo.write(self.owner, row['content'], 'fact', str(uuid4()), origin='ai', scope=scope,
            memory_id=memory['id'], expected_revision=1)
        self.assertEqual(outcome['outcome'], 'conflict')
        self.assertEqual(self.repo.detail(self.owner, memory['id'])['content'], memory['content'])
    def test_public_contracts_do_not_import_infrastructure(self):
        import subprocess, sys
        subprocess.run([sys.executable, '-c', "import app.history_management, sys; assert 'sqlalchemy' not in sys.modules; assert 'langchain_core' not in sys.modules"], check=True, capture_output=True)
    def test_tool_limits_unknown_calls_and_provider_fallback(self):
        row, scope = self.question()
        management = HistoryManagement(self.repo, self.reader, MemoryValidator(Verifier()))
        class BadModel:
            calls = 0
            def bind_tools(self, tools): return self
            async def ainvoke(self, messages):
                self.calls += 1
                return AIMessage(content='', tool_calls=[dict(name='not_a_tool', args={}, id='bad_'+str(self.calls), type='tool_call')])
        class Factory:
            def get_model(self): return model
        model = BadModel()
        with self.assertRaises(AppError): asyncio.run(ChatService(Factory()).reply([('user', row['content'])], history_runtime=(management, self.owner, scope)))
        self.assertLessEqual(model.calls, 5)
        class NoTools:
            async def ainvoke(self, messages): return AIMessage(content='Tools unavailable; general answer.')
        model = NoTools()
        answer = asyncio.run(ChatService(Factory()).reply([('user', row['content'])], history_runtime=(management, self.owner, scope)))
        self.assertIn('Tools unavailable', answer)
    def test_malformed_provider_tool_call_is_clean_failure(self):
        row, scope = self.question()
        management = HistoryManagement(self.repo, self.reader, MemoryValidator(Verifier()))
        class Model:
            def bind_tools(self, tools): return self
            async def ainvoke(self, messages):
                return AIMessage(content='', invalid_tool_calls=[dict(name='user_memory', args='{not json', id='invalid_call', error='bad JSON', type='invalid_tool_call')])
        class Factory:
            def get_model(self): return Model()
        with self.assertRaises(AppError):
            asyncio.run(ChatService(Factory()).reply([('user',row['content'])], history_runtime=(management,self.owner,scope)))
    def test_repeated_lookup_deduplicates_database_work(self):
        from app.history_management.tools import create_history_tools
        row, scope = self.question()
        class CountingReader:
            calls = 0
            def lookup(self, *args): self.calls += 1; return []
        reader = CountingReader(); management = HistoryManagement(self.repo, reader, MemoryValidator(Verifier()))
        tools = create_history_tools(management, self.owner, scope, ToolBudget())
        async def repeated():
            for _ in range(3): await tools[0].ainvoke({'query':'diagrams'})
        asyncio.run(repeated())
        self.assertEqual(reader.calls, 1)
    def test_history_dates_selected_scope_unicode_and_sequence_limits(self):
        row, scope = self.question('图表偏好 ' + uuid4().hex)
        self.chat.finish(self.owner, scope, dict(content='Unicode diagram response'))
        windows = self.reader.lookup(self.owner, scope['conversation_id'], 3, HistoryLookup(query='图表偏好', after_sequence=0, created_before=now()+timedelta(days=1)))
        self.assertTrue(windows)
        self.assertFalse(self.reader.lookup(self.owner, scope['conversation_id'], 3, HistoryLookup(query='图表偏好', created_before=now()-timedelta(days=1))))
        self.assertFalse(self.reader.lookup(self.owner, scope['conversation_id'], 1, HistoryLookup(query='图表偏好')))
        with self.assertRaises(AppError):
            self.reader.lookup(self.owner, scope['conversation_id'], 3, HistoryLookup(scope='selected_chats', query='diagram', chat_ids=[uuid4()]))
        with self.assertRaises(ValueError): HistoryLookup(before_sequence=2, after_sequence=1)
    def test_call_write_and_unicode_result_budgets(self):
        budget = ToolBudget()
        for _ in range(6): budget.call()
        with self.assertRaises(AppError): budget.call()
        budget = ToolBudget()
        budget.call(True); budget.call(True)
        with self.assertRaises(AppError): budget.call(True)
        with self.assertRaises(AppError): ToolBudget().consume('😀'*4000)
    def test_maintenance_preserves_confirmed_and_pinned_records(self):
        from sqlalchemy import update
        row, scope = self.question()
        pinned = self.propose(row, scope, Verifier(explicit=False))['memory']['id']
        self.repo.edit(self.owner, pinned, MemoryEdit(expected_revision=1, pinned=True))
        row, scope = self.question()
        candidate = self.propose(row, scope, Verifier(explicit=False))['memory']['id']
        saved = self.manual()['id']
        with self.db.sessions.begin() as session:
            session.execute(update(memories).where(memories.c.id.in_([pinned,candidate,saved])).values(updated_at=now()-timedelta(days=180)))
        result = self.repo.maintain(self.owner)
        self.assertGreaterEqual(result['expired_candidates'], 1)
        self.assertEqual(self.repo.detail(self.owner,pinned)['status'], 'pending')
        self.assertEqual(self.repo.detail(self.owner,saved)['status'], 'active')
        with self.assertRaises(AppError): self.repo.detail(self.owner,candidate)
    def test_recall_uses_live_profile_facade_without_persisting_a_copy(self):
        from types import SimpleNamespace
        class Details:
            def model_dump(self, **kwargs): return dict(field_of_study='Current physics', learning_goal='Build simulations')
        class Profile:
            def get(self, owner): return SimpleNamespace(details=Details())
        row, scope = self.question()
        management = HistoryManagement(self.repo,self.reader,MemoryValidator(Verifier()),Profile())
        result = asyncio.run(management.memory(self.owner, scope, MemoryToolInput(action='recall',query='study'),ToolBudget()))
        self.assertEqual(result['current_profile']['field_of_study'],'Current physics')
        self.assertFalse(self.repo.list(self.owner,'Current physics')['items'])
    def test_real_tool_loop_remembers_and_retrieves(self):
        owner = self.owner
        verifier = Verifier()
        management = HistoryManagement(self.repo, self.reader, MemoryValidator(verifier))
        class Model:
            seen = []
            def bind_tools(self, tools, **kwargs): return self
            async def ainvoke(self, messages):
                self.seen = messages
                results = [x for x in messages if isinstance(x, ToolMessage)]
                if results: return AIMessage(content='', tool_calls=[dict(name='NewChatReply',
                    args=dict(content='Saved this preference.', conversation_title='Learning with Flowcharts'),
                    id='final_answer', type='tool_call')])
                system = str(messages[0].content)
                data = json.loads(system[system.rfind('\n\n{')+2:])
                question = next(x.content for x in reversed(messages) if x.type == 'human')
                return AIMessage(content='', tool_calls=[dict(name='user_memory', args=dict(action='remember', content=question,
                    category='preference', evidence_message_id=data['history_scope']['current_user_message_id'], evidence_quote=question,
                    tool_name='user_memory', user_message='Checking your saved memories'), id='call_1', type='tool_call')])
        class Factory:
            def get_model(self): return model
        model = Model(); chat_service = ChatService(Factory())
        conversation = ConversationService(self.chat)
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='I prefer flowcharts '+uuid4().hex)
        async def generate(history, selection, scope):
            answer = await chat_service.reply(history, history_runtime=(management, owner, scope))
            return dict(content=answer)
        result = asyncio.run(conversation.send(owner, request, generate, with_scope=True))
        self.assertEqual(result['turn']['state'], 'SUCCEEDED')
        self.assertTrue(any(isinstance(x, ToolMessage) for x in model.seen))
        self.assertTrue(self.repo.list(owner, request.content, recall=True)['items'])


class MigrationRehearsal(unittest.TestCase):
    def test_additive_upgrade_downgrade_preserves_chat(self):
        with PostgresSandbox() as db:
            repo = ChatRepository(db.sessions)
            owner = learner_id('alice')
            request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Preserve this question')
            job = repo.begin_turn(owner, request)
            repo.finish(owner, job, dict(content='Preserve this answer'))
            with db.engine.connect() as connection:
                command.downgrade(migration_config(connection), '20261008_0005')
            upgrade(db.engine)
            self.assertEqual([x['content'] for x in repo.history(owner, str(request.conversation_id))['items']], ['Preserve this question','Preserve this answer'])


if __name__ == '__main__': unittest.main()
