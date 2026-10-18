"""Bind private grading checkpoints to an exact immutable assessment/answer revision."""
from app.history_management.repositories.events.postgres import request_hash

GRADING_TIMEOUT_SECONDS = 120
GRADING_LEASE_SECONDS = 180


def grading_signature(job):
    payload = dict(questions=job['assessment']['questions'], answers=job['attempt']['answers'],
        preferences=job['assessment'].get('preferences', {}),
        grade_revision=job['attempt'].get('grade_revision',1), policy='assessment-grading-v5')
    if job['assessment'].get('practice_lineage'):
        payload['practice_lineage'] = job['assessment']['practice_lineage']
    return request_hash(payload)
