"""The declared expression index must exist after real migrations."""
import os
import unittest
from uuid import uuid4
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from app.db.migrate import migration_config, upgrade
from app.rag.repositories.tables import chunks


class LexicalMetadataTests(unittest.TestCase):
    def test_expression_index_is_attached_to_table(self):
        self.assertIn('idx_rag_chunk_lexical',{index.name for index in chunks.indexes})


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Requires disposable PostgreSQL')
class LexicalMigrationTests(unittest.TestCase):
    def fixture(self):
        from tests.rag.test_workflows import WorkflowTests
        fixture=WorkflowTests(); fixture.setUp(); fixture.ready()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def downgrade_index(self, fixture):
        with fixture.db.engine.connect() as connection:
            command.downgrade(migration_config(connection),'20261029_0038')
            connection.commit()

    def test_upgrade_downgrade_upgrade_retains_canonical_chunks(self):
        fixture=self.fixture()
        with fixture.db.sessions() as session:
            before=[dict(row) for row in session.execute(select(chunks)).mappings()]
        self.downgrade_index(fixture)
        upgrade(fixture.db.engine)
        with fixture.db.sessions() as session:
            self.assertEqual([dict(row) for row in session.execute(select(chunks)).mappings()],before)
            self.assertTrue(session.scalar(text("SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='idx_rag_chunk_lexical' AND n.nspname=current_schema()")))

    def test_retry_repairs_invalid_concurrent_index(self):
        fixture=self.fixture(); self.downgrade_index(fixture)
        with fixture.db.sessions.begin() as session:
            row=dict(session.execute(select(chunks)).mappings().first())
            session.execute(chunks.insert(),dict(row,id=str(uuid4()),ordinal=row['ordinal']+1))
        with fixture.db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            with self.assertRaises(IntegrityError):
                connection.execute(text('CREATE UNIQUE INDEX CONCURRENTLY idx_rag_chunk_lexical ON rag_chunk(content)'))
        upgrade(fixture.db.engine)
        with fixture.db.sessions() as session:
            self.assertTrue(session.scalar(text("SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='idx_rag_chunk_lexical' AND n.nspname=current_schema()")))

    def test_retry_keeps_an_existing_valid_index(self):
        fixture=self.fixture()
        query=text("SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='idx_rag_chunk_lexical' AND n.nspname=current_schema()")
        with fixture.db.engine.connect() as connection:
            before=connection.scalar(query); connection.commit()
            command.downgrade(migration_config(connection),'20261103_0039'); connection.commit()
            command.stamp(migration_config(connection),'20261029_0038'); connection.commit()
        upgrade(fixture.db.engine)
        with fixture.db.engine.connect() as connection:
            self.assertEqual(connection.scalar(query),before)
