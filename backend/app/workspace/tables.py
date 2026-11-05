from sqlalchemy import Column, DateTime, ForeignKey, Table, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.auth.repositories.tables import learner  # noqa: F401
from app.db.metadata import metadata

pins = Table('workspace_source_pin', metadata,
    Column('learner_id', Uuid(as_uuid=False), ForeignKey('learner.id', ondelete='CASCADE'), primary_key=True),
    Column('id', Uuid(as_uuid=False), primary_key=True),
    Column('resource_key', Text, nullable=False),
    Column('source', JSONB, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    UniqueConstraint('learner_id', 'resource_key', name='workspace_source_pin_resource'))
