"""Bounded, owner-scoped live task projection shared by history and status."""
from copy import deepcopy
from sqlalchemy import select
from app.langchain.task_outcomes import legacy_outcome


def project_outcomes(session, owner, messages):
    from app.assessments.repositories.tables import generation_jobs, attempts
    ids = {'generation':set(), 'grading':set()}
    for message in messages:
        for task in (message.get('response_outcome') or {}).get('tasks', []):
            if task.get('job_id') and task.get('job_kind') in ids:
                ids[task['job_kind']].add(task['job_id'])
    records = {}
    for kind, table in (('generation', generation_jobs), ('grading', attempts)):
        if ids[kind]:
            for row in session.execute(select(table.c.id, table.c.state, table.c.revision).where(
                    table.c.learner_id == owner, table.c.id.in_(ids[kind]))).mappings():
                records[(kind,str(row['id']))] = row
    result = []
    for message in messages:
        if not message.get('response_outcome'):
            result.append(message)
            continue
        item = dict(message, response_outcome=deepcopy(message['response_outcome']))
        outcome = item['response_outcome']
        previous_state,previous_retryable=outcome['state'],outcome.get('retryable',False)
        live = []
        inputs=[card for card in item.get('interactions',[]) if card.get('kind')!='value_bars']
        if inputs and all(card.get('submitted_turn_id') for card in inputs):
            from app.langchain.capabilities import PRESENTATIONS
            resolved={task['id'] for task in outcome.get('tasks',[]) if task.get('operation') in PRESENTATIONS}
            for task in outcome.get('tasks',[]):
                if task['state']=='awaiting_input' and (task.get('operation') in PRESENTATIONS or
                        task.get('receipt_ids') and set(task['receipt_ids'])<=resolved):
                    task['state']='completed'
            live.append(dict(retryable=False))
        for task in outcome.get('tasks', []):
            if task.get('job_id'):
                row = records.get((task.get('job_kind'), task['job_id']))
                task['state'] = ('completed' if row['state'] in ('completed','graded') else
                    'paused' if row['state'] == 'stopped' else 'awaiting_input' if row['state'] in ('draft','pending_transcription') else 'in_progress' if row['state'] in ('queued','running','grading','submitted') else 'failed') if row else 'failed'
                task['job_revision'] = row['revision'] if row else None
                task['retryable'] = bool(row and row['state'] == 'failed')
                live.append(task)
        if live:
            outcome.pop('control_action', None)
            states = [task['state'] for task in outcome['tasks'] if task.get('required',True) and (
                not task.get('declared') or task['state'] in ('failed','partial') or not task.get('receipt_ids'))]
            outcome['state'] = ('partial' if 'partial' in states or 'failed' in states and any(value != 'failed' for value in states) else 'failed' if 'failed' in states else
                'paused' if 'paused' in states else 'in_progress' if 'in_progress' in states else 'awaiting_input' if 'awaiting_input' in states else 'completed')
            if previous_state in ('partial','failed') and outcome.get('reason_code')=='REQUEST_OUTCOME_INCOMPLETE' and outcome['state'] not in ('partial','failed'):
                outcome['state']=previous_state
            outcome['retryable'] = outcome['state'] in ('partial','failed') and (any(
                task.get('required',True) and task['state'] in ('partial','failed') and task.get('retryable') for task in outcome['tasks']) or
                previous_retryable and any(task.get('declared') and task['state'] in ('partial','failed') for task in outcome['tasks']))
            retry = next((task for task in live if task.get('retryable') and task.get('job_kind')=='generation'), None)
            if retry:
                outcome['control_action'] = dict(kind='generation_retry', id=retry['job_id'], revision=retry['job_revision'])
            elif (retry := next((task for task in live if task.get('retryable') and task.get('job_kind')=='grading'), None)):
                outcome['control_action'] = dict(kind='grading_retry', id=retry['job_id'], revision=retry['job_revision'])
        result.append(item)
    return result


def turn_outcome(turn, messages):
    message = next((item for item in messages if item.get('sequence') == turn.get('assistant_sequence')), None)
    if turn.get('state') == 'FAILED' and turn.get('error') != 'Response stopped.' and turn.get('response_outcome'):
        return legacy_outcome(turn)
    return (message or {}).get('response_outcome') or legacy_outcome(turn, message)
