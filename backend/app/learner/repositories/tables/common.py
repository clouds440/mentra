"""Native PostgreSQL column helpers used only by repositories."""
from sqlalchemy import Column, Text, Uuid, ForeignKey, DateTime, func
from app.db.metadata import metadata
from app.auth.repositories.tables import learner


def identifier(name='id', *, primary_key=False, nullable=False):
    if name == 'learner_id':
        return Column(name, Uuid(as_uuid=False), ForeignKey('learner.id'), primary_key=primary_key, nullable=nullable)
    return Column(name, Text, primary_key=primary_key, nullable=nullable)


def timestamp(name, *, nullable=False):
    return Column(name, DateTime(timezone=True), nullable=nullable,
                  server_default=None if nullable else func.now())
