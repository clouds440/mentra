"""Minimal durable interrupt; Events owns decisions and business commits."""
from typing import TypedDict
from contextlib import contextmanager
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from app.langchain.repositories.checkpointer import postgres_saver


class EventConfirmationState(TypedDict):
    proposal_id: str
    workflow_version: str
    decision: str


from app.core.logging import workflow_logger

@workflow_logger.operation(outcome='deferred')
def review(state: EventConfirmationState):
    return {'decision': interrupt({'proposal_id': state['proposal_id'], 'workflow_version': state['workflow_version']})}


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class EventConfirmationGraph:
    def __init__(self, engine, workflow_version='event-confirmation-v1'):
        self.engine = engine
        self.workflow_version = workflow_version
        builder = StateGraph(EventConfirmationState)
        builder.add_node('review', review)
        builder.add_edge(START, 'review')
        builder.add_edge('review', END)
        self.builder = builder

    @contextmanager
    def _session(self, owner, proposal_id):
        with postgres_saver(self.engine) as saver:
            thread = f'{self.workflow_version}:{owner}:{proposal_id}'
            # Serialize checkpoint initialization/resume across server processes.
            saver.conn.execute('SELECT pg_advisory_lock(hashtextextended(%s, 0))', (thread,))
            try:
                graph = self.builder.compile(checkpointer=saver)
                config = {'configurable': {'thread_id': thread}, 'recursion_limit': 5}
                yield graph, config
            finally:
                saver.conn.execute('SELECT pg_advisory_unlock(hashtextextended(%s, 0))', (thread,))

    def prepare(self, owner, proposal_id):
        """Establish the real durable pause before displaying a pending proposal."""
        with self._session(owner, proposal_id) as (graph, config):
            if not graph.get_state(config).values:
                graph.invoke({'proposal_id': proposal_id, 'workflow_version': self.workflow_version}, config)

    def decide(self, owner, proposal_id, decision):
        with self._session(owner, proposal_id) as (graph, config):
            snapshot = graph.get_state(config)
            if not snapshot.values:
                graph.invoke({'proposal_id': proposal_id, 'workflow_version': self.workflow_version}, config)
                snapshot = graph.get_state(config)
            if snapshot.next:
                result = graph.invoke(Command(resume=decision), config)
            else:
                result = snapshot.values
            if result.get('decision') != decision:
                from app.core.exceptions import AppError
                raise AppError('PROPOSAL_DECISION_CONFLICT', 'A different decision was already submitted.', 409)
            return result
