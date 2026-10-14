"""Bind private grading checkpoints to an exact immutable assessment/answer revision."""
from app.history_management.repositories.events.postgres import request_hash


def grading_signature(job):
    return request_hash(dict(questions=job['assessment']['questions'], answers=job['attempt']['answers'],
        preferences=job['assessment'].get('preferences', {}),
        grade_revision=job['attempt'].get('grade_revision',1), policy='assessment-grading-v5'))
