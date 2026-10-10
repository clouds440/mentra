"""Shared owner-first write boundary, compatible with existing chat serialization.

Use the existing chat sync row: introducing a second advisory lock would leave
chat deletion and publication outside the boundary. Never hold it over I/O.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert


def lock_owner(session, owner: str):
    from app.chat.repositories.tables import sync_state
    session.execute(insert(sync_state).values(learner_id=owner, revision=0, floor=0).on_conflict_do_nothing())
    return session.execute(select(sync_state).where(sync_state.c.learner_id == owner).with_for_update()).mappings().one()


@dataclass(frozen=True)
class OwnedUnitOfWork:
    """Opaque domain token. Only persistence adapters access the bound session."""
    owner: str
    _session: object


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success', policies={'write': {'kind':'contextmanager'}})
class OwnerTransactions:
    def __init__(self, sessions, *, timeout_ms=5000):
        if not 1 <= timeout_ms <= 300000:
            raise ValueError('Choose a transaction query timeout from 1 to 300000 milliseconds.')
        self.sessions = sessions
        self.timeout_ms = timeout_ms

    @contextmanager
    def write(self, owner: str):
        with self.sessions.begin() as session:
            session.execute(text("SELECT set_config('lock_timeout', :timeout, true), set_config('statement_timeout', :timeout, true)"),
                            {'timeout':f'{self.timeout_ms}ms'})
            lock_owner(session, owner)
            yield OwnedUnitOfWork(owner, session)
