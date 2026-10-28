"""Async LangGraph persistence through short, owner/attempt-fenced transactions.

No database connection is held while a model or domain tool is running.
"""
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import AppError
from .checkpointer import postgres_saver


def response_thread(owner, turn):
    return f'response-v1:{owner}:{turn}'


def delete_response_checkpoints(session, owner, turn):
    from sqlalchemy import text
    for table in ('checkpoint_writes', 'checkpoint_blobs', 'checkpoints'):
        session.execute(text(f'DELETE FROM {table} WHERE thread_id IN (:response, :tools)'),
                        {'response': response_thread(owner, turn) + ':response',
                         'tools': response_thread(owner, turn) + ':tools'})


class ResponseSaver(BaseCheckpointSaver):
    def __init__(self, engine, owner, job):
        super().__init__()
        self.engine, self.owner, self.job = engine, owner, job

    def _call(self, method, *args):
        with postgres_saver(self.engine) as saver, saver.conn.transaction():
            saver.serde = JsonPlusSerializer(allowed_msgpack_modules=[
                ('app.chat.titles', 'NewChatReply'), ('app.langchain.tool_policy', 'DirectAnswer'),
                ('app.langchain.tool_policy', 'DirectNewChatReply')])
            # Same owner-first lock as Stop, Resume, deletion and publication.
            saver.conn.execute('SELECT learner_id FROM chat_sync_state WHERE learner_id=%s FOR UPDATE', (self.owner,))
            row = saver.conn.execute('''SELECT t.state, t.attempt, t.lease_until > now() AS live
                FROM chat_turn t JOIN chat_conversation c ON c.id=t.conversation_id
                WHERE t.learner_id=%s AND t.id=%s AND c.deleted_at IS NULL''',
                (self.owner, self.job['turn_id'])).fetchone()
            if not row or row['state'] != 'RUNNING' or row['attempt'] != self.job['attempt'] or not row['live']:
                raise AppError('CHAT_ATTEMPT_EXPIRED', 'This response is no longer running.', 409)
            return getattr(saver, method)(*args)

    async def aget_tuple(self, config):
        return await run_in_threadpool(self._call, 'get_tuple', config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await run_in_threadpool(self._call, 'put', config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=''):
        return await run_in_threadpool(self._call, 'put_writes', config, writes, task_id, task_path)


def response_config(owner, job, namespace):
    return {'configurable': {'thread_id': response_thread(owner, job['turn_id']) + ':' + namespace,
                            'checkpoint_ns': ''}, 'recursion_limit': 16}
