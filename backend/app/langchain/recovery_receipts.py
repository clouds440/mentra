"""Private completed-write continuity independent of replaceable read context."""
from copy import deepcopy


def partial_response(scope, reason_code):
    """Publish validated native output after synthesis fails, without another call."""
    cards = {key:deepcopy(scope[key]) for key in (
        'assessment_cards','interactions','event_proposals','event_references') if scope.get(key)}
    if not cards:
        return None
    from app.chat.response import ChatResponse
    from .decision_schemas import ResponseOutcome
    outcome = ResponseOutcome(state='partial',retryable=True,reason_code=reason_code,
        tasks=[*scope.get('_task_receipts',{}).values(),
            dict(id='response_synthesis',state='failed',required=True,declared=True,retryable=True)])
    response = ChatResponse(content='I couldn’t finish the response. You can use the available results here and retry the unfinished part.',
        response_outcome=outcome.model_dump(mode='json'),**cards)
    return response.model_dump(mode='json')


def capture_recovery(scope):
    return dict(version=1,results=deepcopy(scope.get('_committed_tool_results',{})),
        cards={key:deepcopy(scope[key]) for key in ('assessment_cards','event_proposals','event_references') if scope.get(key)},
        receipts={key:deepcopy(task) for key,task in scope.get('_task_receipts',{}).items()
                  if task.get('effect_certainty') in ('committed','unknown')},
        failed={key.split(':',1)[0]+':uncertain':deepcopy(value) for key,value in scope.get('_tool_execution_state',{}).get('failed',{}).items()
                if value.get('effect_certainty')=='unknown'})


def restore_recovery(scope):
    value=scope.get('recovery_state')
    if not value or value.get('version')!=1: return
    scope.setdefault('_committed_tool_results',{}).update(deepcopy(value.get('results',{})))
    scope.setdefault('_task_receipts',{}).update(deepcopy(value.get('receipts',{})))
    for key,cards in value.get('cards',{}).items():
        if key in ('assessment_cards','event_proposals','event_references') and not scope.get(key):
            scope[key]=deepcopy(cards)
    execution=scope.setdefault('_tool_execution_state',dict(failed={},results={},outages={}))
    execution.setdefault('failed',{}).update(deepcopy(value.get('failed',{})))
