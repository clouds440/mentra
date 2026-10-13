"""Private summaries, with durable single-flight leases and fenced publication."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from .tables import summaries as s
from .postgres import now


class SummaryRepository:
    def __init__(self, chats):
        self.chats = chats

    def load(self, owner, chat):
        with self.chats.sessions() as session:
            self.chats._conversation(session, owner, chat)
            row = session.execute(select(s).where(s.c.conversation_id == chat, s.c.learner_id == owner)).mappings().first()
            return dict(row) if row else None

    def claim(self, owner, chat):
        with self.chats.sessions.begin() as session:
            self.chats._conversation(session, owner, chat, lock=True)
            session.execute(insert(s).values(conversation_id=chat, learner_id=owner, content='', through_sequence=0,
                revision=0).on_conflict_do_nothing())
            row = dict(session.execute(select(s).where(s.c.conversation_id == chat).with_for_update()).mappings().one())
            if row['lease_until'] and row['lease_until'] > now():
                return None
            token = str(uuid4())
            session.execute(update(s).where(s.c.conversation_id == chat).values(lease_token=token, lease_until=now()+timedelta(seconds=120)))
            return dict(row, lease_token=token)

    def publish(self, owner, chat, claim, content, through):
        with self.chats.sessions.begin() as session:
            self.chats._conversation(session, owner, chat, lock=True)
            result = session.execute(update(s).where(s.c.conversation_id == chat, s.c.learner_id == owner,
                s.c.lease_token == claim['lease_token'], s.c.revision == claim['revision'],
                s.c.lease_until > now(), s.c.through_sequence < through).values(content=content,
                through_sequence=through, revision=claim['revision']+1, lease_token=None, lease_until=None))
            return bool(result.rowcount)

    def release(self, owner, chat, token, *, failed=False):
        with self.chats.sessions.begin() as session:
            session.execute(update(s).where(s.c.conversation_id == chat, s.c.learner_id == owner,
                s.c.lease_token == token).values(lease_token=None,
                    lease_until=now()+timedelta(hours=1) if failed else None))
