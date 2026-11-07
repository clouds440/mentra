"""Private operator review of reported items; no automatic model adjudication."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import and_, or_, select
from app.core.exceptions import AppError
from app.history_management.repositories.events.postgres import request_hash
from ..quality import stored_question
from ..schemas import GeneratedQuestion
from .tables import item_reviews, assessments


def pending_reports(repository, owner, *, after=None, limit=50):
    if not 1 <= limit <= 100:
        raise ValueError('Choose a page size from 1 to 100.')
    newer = item_reviews.alias('newer_review')
    query = select(item_reviews.c.id, item_reviews.c.assessment_id, item_reviews.c.question_id,
        item_reviews.c.reason, item_reviews.c.created_at, assessments.c.title,
        assessments.c.revision.label('assessment_revision')).join(assessments, and_(
            assessments.c.id == item_reviews.c.assessment_id,
            assessments.c.learner_id == item_reviews.c.learner_id)).where(
        item_reviews.c.learner_id == owner, item_reviews.c.decision == 'invalidated',
        ~select(newer.c.id).where(newer.c.learner_id == item_reviews.c.learner_id,
            newer.c.assessment_id == item_reviews.c.assessment_id,
            newer.c.question_id == item_reviews.c.question_id,
            newer.c.revision > item_reviews.c.revision).exists())
    if after:
        stamp, identifier = after.rsplit('|', 1)
        stamp, identifier = datetime.fromisoformat(stamp), str(UUID(identifier))
        if stamp.tzinfo is None:
            raise ValueError('Review cursor must include a timezone.')
        query = query.where(or_(item_reviews.c.created_at > stamp,
            and_(item_reviews.c.created_at == stamp, item_reviews.c.id > identifier)))
    with repository.sessions() as session:
        rows = [dict(row) for row in session.execute(query.order_by(
            item_reviews.c.created_at, item_reviews.c.id).limit(limit + 1)).mappings()]
    items = rows[:limit]
    cursor = f"{items[-1]['created_at'].isoformat()}|{items[-1]['id']}" if len(rows) > limit else None
    return dict(items=items, next_cursor=cursor)


def reported_item(repository, owner, report_id):
    with repository.sessions() as session:
        row = session.execute(select(item_reviews).where(item_reviews.c.learner_id == owner,
            item_reviews.c.id == report_id, item_reviews.c.decision == 'invalidated')).mappings().first()
        if not row:
            raise AppError('ASSESSMENT_REPORT_NOT_FOUND', 'Report unavailable.', 404)
        assessment = repository._assessment(session, owner, row['assessment_id'])
    question = next(question for question in assessment['questions'] if question['id'] == row['question_id'])
    # Explicit private operator output: never expose this through a learner route.
    return dict(report_id=row['id'], assessment_id=row['assessment_id'], question_id=row['question_id'],
        reason=row['reason'], details=row['details'], reported_revision=row['revision']-1,
        original_question=row['previous_question'], expected_revision=assessment['revision'],
        pending=question.get('validation', {}).get('state') == 'invalidated',
        correction_template={key: value for key, value in question.items() if key in GeneratedQuestion.model_fields})


def correct_report(repository, owner, report_id, correction, *, expected_revision, operation_id, apply_digest=None):
    report = reported_item(repository, owner, report_id)
    correction = GeneratedQuestion.model_validate(correction)
    if set(correction.concept_ids) != set(report['correction_template']['concept_ids']):
        raise AppError('ASSESSMENT_REVIEW_TARGET', 'Corrections must retain original learning identities.', 409)
    stored_question(correction, report['question_id'])  # Admission applies to preview and commit.
    digest = request_hash(dict(owner=owner, report_id=report_id, expected_revision=expected_revision,
        operation_id=operation_id, correction=correction.model_dump(mode='json')))
    if apply_digest is None:
        if not report['pending'] or report['expected_revision'] != expected_revision:
            raise AppError('REVISION_CONFLICT', 'Report resolved or assessment changed. Inspect it again.', 409)
        return dict(applied=False, digest=digest, assessment_id=report['assessment_id'],
            question_id=report['question_id'], expected_revision=expected_revision,
            effect='Correct the item and requeue submitted answers for grading; retain originals and history.')
    if apply_digest != digest:
        raise AppError('ASSESSMENT_REVIEW_PREVIEW_CHANGED', 'The correction changed after preview.', 409)
    value = repository.review_item(owner, report['assessment_id'], report['question_id'], expected_revision,
        operation_id, 'trusted_correction', correction=correction)
    return dict(applied=True, assessment_id=str(value.id), revision=value.revision)
