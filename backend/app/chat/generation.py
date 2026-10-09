"""Compatibility adapter for existing API callers; orchestration owns AI execution."""
from app.langchain.orchestration_service import OrchestrationService


async def generate_reply(messages, retrieval, http_request, identity, history_policy=None, history_scope=None):
    state = http_request.app.state
    orchestration = getattr(state, 'orchestration_service', None) or OrchestrationService(
        state.chat_service, rag=getattr(state, 'rag_service', None),
        learner=getattr(state, 'learner_service', None), history=getattr(state, 'history_management', None))
    return await orchestration.chat_reply(messages, retrieval, getattr(identity, 'learner_id', None), history_policy, history_scope)
