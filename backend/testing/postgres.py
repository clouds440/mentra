"""Each test uses a unique schema; TEST_DATABASE_URL is always explicit."""

import os
import re
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.database import build_engine
from app.db.urls import postgres_url
from app.db.migrate import upgrade
from app.learner.repositories.postgres import PostgresLearnerRepository
from app.auth.repositories.tables import learner
from testing.identities import TEST_LEARNERS, learner_id


class PostgresSandbox:
    def __init__(self, *, seed_learners=True):
        url = os.environ.get('TEST_DATABASE_URL', '')
        if not url:
            raise RuntimeError('Set TEST_DATABASE_URL to a dedicated PostgreSQL test database; DATABASE_URL is never used for tests')
        self.schema = 'mentra_test_' + uuid4().hex
        self.admin = build_engine(url, connect_args={'connect_timeout': 5})
        with self.admin.begin() as connection:
            connection.execute(CreateSchema(self.schema))
        self.engine = build_engine(postgres_url(url).update_query_dict({'options': '-csearch_path=' + self.schema}).render_as_string(hide_password=False), connect_args={'connect_timeout': 5})
        self.connections = 0
        event.listen(self.engine, 'checkout', self._checkout)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.repository = PostgresLearnerRepository(self.sessions)
        try:
            upgrade(self.engine)
            if seed_learners:
                with self.engine.begin() as connection:
                    connection.execute(learner.insert(), [{'id': learner_id(name)} for name in TEST_LEARNERS])
        except Exception:
            self.close()
            raise

    def _checkout(self, *args):
        self.connections += 1

    def close(self):
        if not re.fullmatch(r'mentra_test_[0-9a-f]{32}', self.schema):
            raise RuntimeError('Refusing to drop an unrecognized test schema')
        self.engine.dispose()
        with self.admin.begin() as connection:
            connection.execute(DropSchema(self.schema, cascade=True))
        self.admin.dispose()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
