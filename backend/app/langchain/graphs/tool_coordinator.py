"""Bounded model/tool cycle; durable effects remain in domain job repositories."""
from typing import Any, TypedDict
from langgraph.graph import StateGraph, START, END


class ToolState(TypedDict, total=False):
    iteration: int
    response: Any
    done: bool


async def coordinate(model_round, dispatch_round):
    builder = StateGraph(ToolState)
    builder.add_node('model', model_round)
    builder.add_node('tools', dispatch_round)
    builder.add_edge(START, 'model')
    builder.add_conditional_edges('model', lambda state: 'answer' if state.get('done') else 'tools',
                                  {'answer': END, 'tools': 'tools'})
    builder.add_edge('tools', 'model')
    # Five model rounds plus four dispatch rounds. Domain subworkflows do not
    # receive this mutable state or reset the shared call/write budgets.
    result = await builder.compile().ainvoke({'iteration': 0}, {'recursion_limit': 12})
    return result['response']
