"""A response is one durable workflow, regardless of how often it is paused."""
from typing import Any, TypedDict
from langgraph.graph import StateGraph, START, END
from app.langchain.repositories.response_checkpoints import ResponseSaver, response_config


class ResponseState(TypedDict, total=False):
    response: Any


async def run_response(generate, engine, owner, job):
    async def answer(state):
        return {'response': await generate()}
    builder = StateGraph(ResponseState)
    builder.add_node('answer', answer)
    builder.add_edge(START, 'answer')
    builder.add_edge('answer', END)
    graph = builder.compile(checkpointer=ResponseSaver(engine, owner, job))
    config = response_config(owner, job, 'response')
    snapshot = await graph.aget_state(config)
    # Cancellation leaves the pending node in LangGraph. Invoking None resumes
    # that node; completed nodes and their domain receipts are retained.
    if snapshot.values and not snapshot.next and not job.get('new_instruction'):
        return snapshot.values['response']
    result = await graph.ainvoke(None if snapshot.created_at and not job.get('new_instruction') else {}, config, durability='sync')
    return result['response']
