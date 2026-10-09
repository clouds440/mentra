"""Pinned PostgresSaver 3.1.2 schema, managed by Alembic."""
from sqlalchemy import Table, Column, Text, Integer, LargeBinary, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.db.metadata import metadata

migrations = Table('checkpoint_migrations', metadata, Column('v', Integer, primary_key=True))
checkpoints = Table('checkpoints', metadata,
    Column('thread_id', Text, primary_key=True), Column('checkpoint_ns', Text, primary_key=True, server_default=''),
    Column('checkpoint_id', Text, primary_key=True), Column('parent_checkpoint_id', Text), Column('type', Text),
    Column('checkpoint', JSONB, nullable=False), Column('metadata', JSONB, nullable=False, server_default='{}'),
    Index('checkpoints_thread_id_idx', 'thread_id'))
blobs = Table('checkpoint_blobs', metadata,
    Column('thread_id', Text, primary_key=True), Column('checkpoint_ns', Text, primary_key=True, server_default=''),
    Column('channel', Text, primary_key=True), Column('version', Text, primary_key=True),
    Column('type', Text, nullable=False), Column('blob', LargeBinary), Index('checkpoint_blobs_thread_id_idx', 'thread_id'))
writes = Table('checkpoint_writes', metadata,
    Column('thread_id', Text, primary_key=True), Column('checkpoint_ns', Text, primary_key=True, server_default=''),
    Column('checkpoint_id', Text, primary_key=True), Column('task_id', Text, primary_key=True), Column('idx', Integer, primary_key=True),
    Column('channel', Text, nullable=False), Column('type', Text), Column('blob', LargeBinary, nullable=False),
    Column('task_path', Text, nullable=False, server_default=''), Index('checkpoint_writes_thread_id_idx', 'thread_id'))


def delete_thread(session, thread_id):
    for table in (writes, blobs, checkpoints):
        session.execute(table.delete().where(table.c.thread_id == thread_id))
