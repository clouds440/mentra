"""Bounded model/tool cycle; durable effects remain in domain job repositories."""
from typing import Any, TypedDict
from langgraph.graph import StateGraph, START, END


class ToolState(TypedDict, total=False):
    finish_decision: dict | None
    iteration: int
    response: Any
    done: bool
    runtime: dict


async def coordinate(model_round, dispatch_round, *, checkpoint=None, capture=None, restore=None, amendment=None, validate=None):
    async def wrapped(node, state):
        if restore and state.get('runtime'):
            restore(state['runtime'])
        if validate: await validate()
        value = await node(state)
        if capture: value['runtime'] = capture()
        return value
    async def model(state): return await wrapped(model_round, state)
    async def tools(state): return await wrapped(dispatch_round, state)
    builder = StateGraph(ToolState)
    builder.add_node('model', model)
    builder.add_node('tools', tools)
    builder.add_edge(START, 'model')
    builder.add_conditional_edges('model', lambda state: 'answer' if state.get('done') else 'tools',
                                  {'answer': END, 'tools': 'tools'})
    builder.add_edge('tools', 'model')
    # Five model rounds plus four dispatch rounds. Domain subworkflows do not
    # receive this mutable state or reset the shared call/write budgets.
    saver, config = None, {'recursion_limit': 12}
    if checkpoint:
        from app.langchain.repositories.response_checkpoints import ResponseSaver, response_config
        engine, owner, job = checkpoint
        saver, config = ResponseSaver(engine, owner, job), response_config(owner, job, 'tools')
    graph = builder.compile(checkpointer=saver)
    snapshot = await graph.aget_state(config) if saver else None
    if snapshot and snapshot.created_at and amendment:
        state = dict(snapshot.values)
        if restore and state.get('runtime'): restore(state['runtime'])
        # A changed instruction starts a new model step from completed receipts.
        # Never run a previously planned write after its instruction changed.
        if capture: state['runtime'] = capture(amendment)
        state.update(iteration=0, response=None, done=False, finish_decision=None)
        await graph.aupdate_state(config, state, as_node='tools')
    elif snapshot and snapshot.created_at and not snapshot.next:
        runtime = snapshot.values.get('runtime', {})
        if restore and runtime: restore(runtime)
        from app.langchain.task_outcomes import incomplete_response
        if checkpoint and runtime.get('attempt',1) != checkpoint[2]['attempt'] and incomplete_response(runtime.get('scope',{})):
            state = dict(snapshot.values, iteration=0, response=None, done=False, finish_decision=None)
            if capture: state['runtime'] = capture()
            await graph.aupdate_state(config, state, as_node='tools')
        else:
            return snapshot.values['response']
    result = await graph.ainvoke(None if snapshot and snapshot.created_at else {'iteration': 0}, config,
        **({'durability':'sync'} if saver else {}))
    return result['response']
