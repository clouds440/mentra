"""Bounded card projections; full papers remain behind the detail endpoint."""
from sqlalchemy import select, func, cast
from sqlalchemy.dialects.postgresql import JSONPATH
from uuid import UUID
from app.assessments.schemas import AttemptSummary
from .tables import assessments as a, attempts as t


def summaries(repository, owner, offset=0):
    with repository.sessions() as session:
        rows = session.execute(select(a.c.id, a.c.title, a.c.purpose, a.c.revision, a.c.created_at,
            (func.jsonb_typeof(a.c.paper) == 'object').label('has_paper'),
            func.jsonb_array_length(a.c.questions).label('part_count'),
            func.coalesce(a.c.paper['question_count'].as_integer(), func.jsonb_array_length(a.c.questions)).label('question_count'),
            a.c.practice_lineage['revision_assessment'].as_boolean().label('revision_assessment'),
            func.jsonb_path_query_array(a.c.questions, cast('$[*].id', JSONPATH)).label('question_ids'),
            func.jsonb_path_query_array(a.c.questions, cast('$[*].marks', JSONPATH)).label('marks'))
            .where(a.c.learner_id == owner).order_by(a.c.created_at.desc(), a.c.id).offset(offset).limit(21)).mappings().all()
        page = rows[:20]
        ids = [row['id'] for row in page]
        history = {}
        if ids:
            latest = select(t.c.assessment_id, t.c.state,
                func.count().over(partition_by=t.c.assessment_id).label('count'))\
                .where(t.c.learner_id == owner, t.c.assessment_id.in_(ids))\
                .distinct(t.c.assessment_id).order_by(t.c.assessment_id, t.c.attempt_number.desc(), t.c.id).subquery()
            graded = select(t.c.assessment_id, t.c.id, t.c.attempt_number, t.c.grades)\
                .where(t.c.learner_id == owner, t.c.assessment_id.in_(ids), t.c.state == 'graded')\
                .distinct(t.c.assessment_id).order_by(t.c.assessment_id, t.c.attempt_number.desc(), t.c.id).subquery()
            history = {row['assessment_id']: row for row in session.execute(select(latest,
                graded.c.id.label('graded_id'), graded.c.attempt_number, graded.c.grades)
                .select_from(latest.outerjoin(graded, latest.c.assessment_id == graded.c.assessment_id))).mappings()}
        items = []
        for row in page:
            attempt = history.get(row['id'])
            summary = AttemptSummary(count=attempt['count'] if attempt else 0,
                latest_state=attempt['state'] if attempt else None)
            if attempt and attempt['graded_id']:
                summary.graded_attempt_id = UUID(attempt['graded_id'])
                summary.graded_attempt_number = attempt['attempt_number']
                grades = {grade['question_id']: grade for grade in attempt['grades'] or []}
                for identifier, marks in zip(row['question_ids'], row['marks']):
                    grade = grades.get(identifier)
                    if grade is None:
                        continue
                    if grade['score'] >= marks:
                        summary.correct += 1
                    else:
                        summary.incorrect += 1
                        summary.partial += int(grade['score'] > 0)
            items.append(dict({key: row[key] for key in ('id', 'title', 'purpose', 'revision', 'created_at',
                'part_count', 'question_count', 'has_paper')}, tags=['revision assessment'] if row['revision_assessment'] else [],
                attempt_summary=summary))
        return dict(items=items, next_offset=offset+20 if len(rows) > 20 else None)
