"""Real PostgreSQL usage races, restart ambiguity, migration and chat publication."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, func, delete, inspect
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.migrate import migration_config, upgrade
from app.db.metadata import metadata
from app.web_search.repositories.postgres import UsageRepository
from app.web_search.repositories.tables import calls, guard, cache
from app.chat.repositories.postgres import ChatRepository
from app.chat.repositories.activity import ActivityRepository
from app.chat.schemas import SendTurn
from app.chat.response import ChatResponse
from app.langchain.activity import ActivityUpdate
from app.web_search.normalization import normalize_results
from app.auth.repositories.tables import learner
from testing.postgres import PostgresSandbox
from testing.identities import learner_id
from tests.test_web_search import PAYLOAD, NOW


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires explicit dedicated PostgreSQL test database')
class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.owner, self.other = learner_id('alice'), learner_id('bob')
        self.usage = UsageRepository(self.db.sessions)
    def tearDown(self): self.db.close()

    def test_authenticated_research_does_not_consume_free_search_quota(self):
        free = UsageRepository(self.db.sessions, global_limit=1)
        research = UsageRepository(self.db.sessions, provider='you_research', global_limit=1)
        self.assertEqual(research.reserve(self.owner, str(uuid4()), NOW), 'reserved')
        self.assertEqual(research.reserve(self.owner, str(uuid4()), NOW), 'quota_exhausted')
        self.assertEqual(free.reserve(self.owner, str(uuid4()), NOW), 'reserved')
        self.assertEqual(free.reserve(self.owner, str(uuid4()), NOW), 'quota_exhausted')

    def test_multiple_workers_race_for_last_global_slot_and_owner_limits(self):
        repo = UsageRepository(self.db.sessions, global_limit=1)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda owner: repo.reserve(owner, str(uuid4()), NOW), (self.owner, self.other)))
        self.assertEqual(sorted(results), ['quota_exhausted', 'reserved'])
        with self.db.sessions.begin() as session: session.execute(delete(calls))
        repo = UsageRepository(self.db.sessions, user_limit=1)
        self.assertEqual(repo.reserve(self.owner, str(uuid4()), NOW), 'reserved')
        self.assertEqual(repo.reserve(self.owner, str(uuid4()), NOW), 'quota_exhausted')
        self.assertEqual(repo.reserve(self.other, str(uuid4()), NOW), 'reserved')

    def test_minute_limit_released_unsent_and_unknown_restart(self):
        repo = UsageRepository(self.db.sessions, minute_limit=1)
        operation = str(uuid4())
        self.assertEqual(repo.reserve(self.owner, operation, NOW), 'reserved')
        repo.mark(operation, 'released')
        operation = str(uuid4())
        self.assertEqual(repo.reserve(self.owner, operation, NOW), 'reserved')
        repo.mark(operation, 'sent')
        repo.mark(operation, 'unknown')
        repo.mark(operation, 'released')  # Cannot refund an ambiguous send.
        fresh = UsageRepository(self.db.sessions, minute_limit=1)
        self.assertEqual(fresh.reserve(self.owner, operation, NOW), 'duplicate')
        self.assertEqual(fresh.reserve(self.owner, str(uuid4()), NOW), 'rate_limited')
        self.assertEqual(fresh.reserve(self.owner, str(uuid4()), NOW + timedelta(minutes=2)), 'reserved')

    def test_anonymized_usage_stays_charged_and_window_expires(self):
        owner = str(uuid4())
        with self.db.sessions.begin() as session: session.execute(learner.insert().values(id=owner))
        repo = UsageRepository(self.db.sessions, global_limit=1)
        operation = str(uuid4())
        self.assertEqual(repo.reserve(owner, operation, NOW), 'reserved')
        # Use FK anonymization directly; chat sync state is part of the existing deletion boundary.
        from app.chat.repositories.tables import sync_state
        with self.db.sessions.begin() as session:
            session.execute(delete(sync_state).where(sync_state.c.learner_id == owner))
            session.execute(delete(learner).where(learner.c.id == owner))
        with self.db.sessions() as session:
            row = session.execute(select(calls).where(calls.c.id == operation)).mappings().one()
            self.assertIsNone(row['learner_id'])
        self.assertEqual(repo.reserve(self.other, str(uuid4()), NOW), 'quota_exhausted')
        self.assertEqual(repo.reserve(self.other, str(uuid4()), NOW + timedelta(days=1, seconds=1)), 'reserved')

    def test_citations_and_website_activity_are_canonical_owned_and_survive_reload(self):
        chat = ChatRepository(self.db.sessions)
        request = SendTurn(conversation_id=uuid4(), client_turn_id=uuid4(), expected_revision=0, content='Search python.org')
        job = chat.begin_turn(self.owner, request)
        source = normalize_results(PAYLOAD, 'python.org', NOW)[0][0].model_copy(update={'token':'W1'})
        update = ActivityUpdate(step_id='search-web', status='running', tool_name='web_search', user_message='Searching python.org',
            websites=[dict(domain='python.org', favicon_url='https://python.org/favicon.ico')])
        activity = ActivityRepository(self.db.sessions)
        activity.append(self.owner, job, update)
        self.assertEqual(activity.page(self.owner, job['conversation_id'], job['turn_id'], 1)['events'][0]['websites'][0]['domain'], 'python.org')
        response = ChatResponse(content='Claim [[W1]]', web_sources=[source], web_citations=['W1'])
        chat.finish(self.owner, job, response.model_dump(mode='json'))
        page = ChatRepository(self.db.sessions).status(self.owner, job['conversation_id'])
        saved = next(item for item in page['items'] if item['role'] == 'assistant')
        self.assertEqual(saved['web_sources'][0]['favicon_url'], source.favicon_url)
        self.assertEqual(saved['web_citations'], ['W1'])

    def test_shared_cache_is_owned_expires_and_has_fixed_global_capacity(self):
        payload = dict(outcome='ok', sources=[])
        expires = NOW + timedelta(seconds=120)
        self.usage.cache_result(self.owner, 'same-query', NOW, expires, payload)
        fresh_worker = UsageRepository(self.db.sessions)
        self.assertEqual(fresh_worker.cached(self.owner, 'same-query', NOW)['payload'], payload)
        self.assertIsNone(fresh_worker.cached(self.other, 'same-query', NOW))
        self.assertIsNone(fresh_worker.cached(self.owner, 'same-query', expires))
        for index in range(130):
            self.usage.cache_result(self.owner, f'query-{index:03}', NOW + timedelta(microseconds=index), expires, payload)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(cache)), 128)
        self.assertIsNone(self.usage.cached(self.owner, 'same-query', NOW))
        self.usage.cache_result(self.owner, 'oversized', NOW, expires, dict(content='x'*32769))
        self.assertIsNone(self.usage.cached(self.owner, 'oversized', NOW))

    def test_migration_down_up_preserves_non_feature_data_and_metadata(self):
        with self.db.engine.connect() as connection:
            before = connection.scalar(select(func.count()).select_from(learner))
            command.downgrade(migration_config(connection), '20261010_0016')
            connection.commit()
            self.assertNotIn('web_search_call', inspect(connection).get_table_names())
            self.assertEqual(connection.scalar(select(func.count()).select_from(learner)), before)
        upgrade(self.db.engine)
        with self.db.engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection, opts={'compare_type': True}), metadata)
            web_differences = [difference for difference in differences if 'web_search' in str(difference)]
            self.assertEqual(web_differences, [])
