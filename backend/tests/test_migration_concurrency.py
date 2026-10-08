"""Concurrent schema rehearsals must not block concurrent-index snapshots."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from time import sleep, monotonic
from sqlalchemy import text
from alembic.script import ScriptDirectory
from app.db.database import build_engine
from app.db.migrate import upgrade, migration_config
from testing.postgres import PostgresSandbox


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires explicit dedicated TEST_DATABASE_URL')
class MigrationConcurrencyTests(unittest.TestCase):
    def test_competing_fresh_schema_migrations_finish_without_deadlock(self):
        def rehearse(_):
            with PostgresSandbox() as db:
                with db.engine.connect() as connection:
                    return connection.scalar(text('SELECT version_num FROM alembic_version'))
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(rehearse, range(2)))
        head = ScriptDirectory.from_config(migration_config()).get_current_head()
        self.assertEqual(results, [head, head])

    def test_migration_lock_wait_is_bounded_and_leaves_no_lock_after_timeout(self):
        engine = build_engine(os.environ['TEST_DATABASE_URL'])
        try:
            with engine.connect() as blocker:
                deadline = monotonic() + 30
                while True:
                    acquired = blocker.scalar(text('SELECT pg_try_advisory_lock(17483, 1)'))
                    blocker.commit()
                    if acquired:
                        break
                    if monotonic() > deadline:
                        self.fail('The test could not acquire its migration lock.')
                    sleep(0.05)
                try:
                    with self.assertRaisesRegex(RuntimeError, 'Timed out'):
                        upgrade(engine, lock_timeout=0.05)
                finally:
                    blocker.execute(text('SELECT pg_advisory_unlock(17483, 1)'))
                    blocker.commit()
                with engine.connect() as verifier:
                    self.assertTrue(verifier.scalar(text('SELECT pg_try_advisory_lock(17483, 1)')))
                    verifier.execute(text('SELECT pg_advisory_unlock(17483, 1)'))
                    verifier.commit()
        finally:
            engine.dispose()
