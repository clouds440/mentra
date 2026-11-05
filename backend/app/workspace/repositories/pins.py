"""Owned source pins with atomic deduplication and capacity enforcement."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4
from sqlalchemy import delete, func, select
from app.auth.repositories.tables import learner
from app.core.exceptions import AppError
from .tables import pins


class PinRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def list(self, owner):
        with self.sessions() as session:
            return [dict(row) for row in session.execute(select(pins.c.id, pins.c.source)
                .where(pins.c.learner_id == owner).order_by(pins.c.created_at.desc(), pins.c.id)).mappings()]

    def add(self, owner, source):
        key = sha256(json.dumps({name: value for name, value in source.items() if name != 'title'}, sort_keys=True).encode()).hexdigest()
        with self.sessions.begin() as session:
            session.execute(select(learner.c.id).where(learner.c.id == owner).with_for_update()).scalar_one()
            old = session.execute(select(pins.c.id, pins.c.source).where(
                pins.c.learner_id == owner, pins.c.resource_key == key)).mappings().first()
            if old:
                return dict(old)
            if session.scalar(select(func.count()).select_from(pins).where(pins.c.learner_id == owner)) >= 100:
                raise AppError('WORKSPACE_PIN_LIMIT', 'Remove a pinned source before adding another. You can keep up to 100 pins.', 422)
            identifier = str(uuid4())
            session.execute(pins.insert().values(learner_id=owner, id=identifier, resource_key=key,
                source=source, created_at=datetime.now(timezone.utc)))
            return dict(id=identifier, source=source)

    def remove(self, owner, identifier):
        with self.sessions.begin() as session:
            session.execute(delete(pins).where(pins.c.learner_id == owner, pins.c.id == identifier))
