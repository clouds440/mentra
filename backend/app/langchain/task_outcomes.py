"""Receipt-backed fulfillment. A successful graph return is not task success."""
from hashlib import sha256
import json
from .decision_schemas import ResponseOutcome
from .capabilities import PRESENTATIONS


def incomplete_response(value):
    return isinstance(value,dict) and ((value.get('response_outcome') or {}).get('state') in ('partial','failed') or
        any(item.get('code')=='REQUEST_OUTCOME_INCOMPLETE' for item in value.get('tool_warnings',[])))


def receipt_id(scope, call_id):
    tasks=scope.get('_task_receipts',{})
    previous=tasks.get(call_id,{}).get('id')
    if previous: return previous
    number=len(tasks)+1
    existing={task['id'] for task in tasks.values()}
    while f'receipt{number}' in existing: number+=1
    return f'receipt{number}'


def record_receipt(scope, call, result):
    if call['name'] == 'enable_workflow_tools':
        return
    from .tool_execution import outcome_status
    from .tool_policy import is_write
    value = result if isinstance(result, dict) else {}
    status, _ = outcome_status(value)
    state = 'failed' if status == 'failed' else 'partial' if status == 'degraded' else 'awaiting_input' if status == 'waiting' else 'completed'
    if call['name'] in PRESENTATIONS:
        state = 'awaiting_input' if call['name'] != 'present_visuals' and status != 'failed' else state
    ref = value.get('generation_job_id') or (value.get('job') or {}).get('id')
    if value.get('state') in ('queued', 'running', 'pending') or value.get('outcome') in ('queued', 'running'):
        state = 'in_progress'
    grading = call['name'] == 'assessment_answer' and value.get('attempt_id')
    if grading:
        state = 'in_progress' if value.get('outcome') in ('submitted', 'grading') else 'completed' if value.get('outcome') == 'graded' else 'awaiting_input' if value.get('outcome') in ('draft','pending_transcription') else state
    tasks = scope.setdefault('_task_receipts', {})
    signature = sha256(json.dumps([call['name'], call['args']], sort_keys=True, default=str).encode()).hexdigest()
    tasks[call['id']] = dict(id=receipt_id(scope,call['id']), operation=call['name'], state=state, signature=signature,
        code=value.get('code'), retryable=bool(value.get('retryable') or value.get('category') in ('transient_dependency','rate_limited','budget_exhausted')),
        effect_certainty=value.get('effect_certainty', 'read_only' if not is_write(call['name'], call['args']) else 'committed' if state in ('completed','in_progress','awaiting_input') else 'not_started'),
        **({'job_id':str(ref), 'job_kind':'generation'} if ref else {'job_id':str(grading), 'job_kind':'grading'} if grading else {}))
    # A corrected argument/protocol request does not leave a permanent failure.
    if state != 'failed':
        for task in tasks.values():
            if task['operation'] == call['name'] and task['state'] == 'failed' and (task.get('signature') == signature or task.get('code') in ('TOOL_INVALID_ARGUMENTS','TOOL_NOT_ENABLED','TOOL_UNKNOWN')):
                task.update(state='completed', superseded_by=call['id'], retryable=False)


def finalize(scope, decision):
    canonical = scope.get('_task_receipts', {})
    # Short server-assigned references reduce copying errors and protocol tokens.
    # Native call IDs remain accepted for retained checkpoints/older providers.
    receipts = {**canonical, **{task['id']:task for task in canonical.values()}}
    jobs={task.get('job_id') for task in canonical.values() if task.get('job_id')}
    for identifier in jobs:
        matches=[task for task in canonical.values() if task.get('job_id')==identifier]
        if len(matches)==1: receipts[identifier]=matches[0]
    unknown = {ref for task in decision.tasks for ref in task.receipt_ids if ref not in receipts}
    if unknown:
        from app.core.exceptions import AppError
        raise AppError('CHAT_INVALID_RECEIPT', 'An action could not be verified. Please retry the unfinished part.', 502)
    for task in decision.tasks:
        if task.state == 'completed' and ((task.grounding=='study_material' and not scope.get('study_sources')) or
                (task.grounding=='web' and not scope.get('web_sources'))):
            from app.core.exceptions import AppError
            raise AppError('CHAT_MISSING_EVIDENCE','The requested source-grounded answer has no verified evidence.',502)
        if task.operation and task.state in ('completed','in_progress') and not any(
                receipts[ref]['operation'] == task.operation and receipts[ref]['state'] in ('completed','in_progress','awaiting_input')
                for ref in task.receipt_ids):
            from app.core.exceptions import AppError
            raise AppError('CHAT_INVALID_RECEIPT', 'The requested action has no matching successful receipt.', 502)
    optional = {receipts[ref]['id'] for task in decision.tasks if not task.required for ref in task.receipt_ids
                if receipts[ref].get('effect_certainty') == 'read_only'}
    tasks = [dict(task, required=task['id'] not in optional) for task in canonical.values() if not task.get('superseded_by')]
    declared = [task.model_dump(mode='json') for task in decision.tasks]
    failed = [task for task in tasks if task['required'] and task['state'] in ('failed','partial')]
    explicit_failed = any(task.required and task.state in ('failed','partial') for task in decision.tasks)
    cards = scope.get('assessment_cards', [])
    usable = any(task['state'] in ('completed','in_progress','awaiting_input') for task in tasks) or bool(cards)
    state = decision.outcome
    if failed or explicit_failed:
        state = 'partial' if usable or decision.outcome == 'partial' else 'failed'
    elif state not in ('failed','partial','paused') and any(task['state'] == 'in_progress' for task in tasks):
        state = 'in_progress'
    elif state not in ('failed','partial','paused') and (any(task['state'] == 'awaiting_input' for task in tasks) or any(
            card.get('kind') != 'value_bars' for card in scope.get('interactions', [])) or scope.get('event_proposals')):
        state = 'awaiting_input'
    if not decision.content.strip() and not usable and not scope.get('interactions'):
        state = 'failed'
        decision.content = 'This request could not be completed. Please retry the unfinished part.'
    retryable = state in ('failed','partial') and (any(task.get('retryable') for task in failed) or not failed)
    outcome = ResponseOutcome(state=state, retryable=retryable,
        reason_code='REQUEST_OUTCOME_INCOMPLETE' if state in ('failed','partial') else None,
        tasks=[*tasks, *[dict(task, declared=True) for task in declared]])
    scope['response_outcome'] = outcome.model_dump(mode='json')
    if decision.conversation_title:
        scope['conversation_title'] = decision.conversation_title
    from app.core.logging import workflow_logger
    workflow_logger.set_outcome('failed' if state == 'failed' else 'degraded' if state == 'partial' else 'deferred' if state in ('awaiting_input','in_progress') else 'success', code=outcome.reason_code)
    return decision


def legacy_outcome(turn, metadata=None):
    saved = turn.get('response_outcome') or (metadata or {}).get('response_outcome')
    if saved:
        return ResponseOutcome.model_validate(saved).model_dump(mode='json')
    warnings = (metadata or {}).get('tool_warnings', [])
    incomplete = any(item.get('code') == 'REQUEST_OUTCOME_INCOMPLETE' for item in warnings)
    state = 'paused' if turn.get('error') == 'Response stopped.' else 'failed' if incomplete or turn.get('state') == 'FAILED' else 'in_progress' if turn.get('state') == 'RUNNING' else 'completed'
    return ResponseOutcome(state=state, legacy=True, retryable=state == 'failed',
        reason_code='LEGACY_INCOMPLETE_RESPONSE' if incomplete else None).model_dump(mode='json')
