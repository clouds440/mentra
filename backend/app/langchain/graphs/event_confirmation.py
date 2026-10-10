"""Minimal durable interrupt; Events owns decisions and business commits."""
from typing import TypedDict
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

    def decide(self, owner, proposal_id, decision):
        with postgres_saver(self.engine) as saver:
            graph = self.builder.compile(checkpointer=saver)
            config = {'configurable': {'thread_id': f'{self.workflow_version}:{owner}:{proposal_id}'}, 'recursion_limit': 5}
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
