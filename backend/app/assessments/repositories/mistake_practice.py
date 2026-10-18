"""Derivative questions keep private keys, immutable snapshots and root item identity."""
from copy import deepcopy
from uuid import uuid4
from sqlalchemy import select, func
from app.core.exceptions import AppError
from app.history_management.repositories.events.postgres import request_hash
from .tables import assessments, practice_operations


def inherit_practice_lineage(repository, session, owner, request, questions, assessment_id):
    """Revising an exposed worksheet cannot turn retained questions into fresh evidence."""
    source = None
    if request.revision_assessment_id:
        source = repository._assessment(session, owner, str(request.revision_assessment_id))
    elif request.revision_draft_id:
        from .chat import ChatAssessmentRepository
        source = ChatAssessmentRepository(repository)._draft(session, owner, str(request.revision_draft_id))['payload']
    lineage = deepcopy(source.get('practice_lineage')) if source else None
    if not lineage: return None
    old_items = lineage['question_items']
    identities = {(q['prompt'], q.get('context', '')):old_items[q['id']] for q in source['questions'] if q['id'] in old_items}
    lineage['question_items'] = {q['id']:identities.get((q['prompt'], q.get('context', '')), f"{assessment_id}:{q['id']}") for q in questions}
    return lineage


def create_practice(repository, owner, identifier, body):
    fingerprint = request_hash(dict(kind='mistake-practice-v1', attempt_id=identifier,
        grade_revision=body.expected_grade_revision, question_ids=sorted(map(str, body.question_ids))))
    with repository.transactions.write(owner) as tx:
        session = tx._session
        receipt = session.execute(select(practice_operations).where(practice_operations.c.learner_id==owner,
            practice_operations.c.operation_id==str(body.client_request_id))).mappings().first()
        if receipt:
            if receipt['fingerprint'] != fingerprint:
                raise AppError('OPERATION_CONFLICT', 'This request ID belongs to different practice.', 409)
            saved = session.execute(select(assessments).where(assessments.c.learner_id==owner,
                assessments.c.id==receipt['assessment_id'])).mappings().first()
            if not saved:
                raise AppError('ASSESSMENT_PRACTICE_DELETED', 'This follow-up was deleted. Choose a new practice request to continue.', 410)
            return repository.public(saved)
        previous = session.execute(select(assessments).where(assessments.c.learner_id==owner,
            assessments.c.operation_id==str(body.client_request_id))).mappings().first()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise AppError('OPERATION_CONFLICT', 'This request ID belongs to different practice.', 409)
            return repository.public(previous)
        attempt = repository._attempt(session, owner, identifier)
        if attempt['state'] != 'graded' or attempt['grade_revision'] != body.expected_grade_revision:
            raise AppError('REVISION_CONFLICT', 'Results changed. Reload before choosing practice questions.', 409)
        source = repository._assessment(session, owner, attempt['assessment_id'])
        grades = {grade['question_id']:grade for grade in attempt['grades'] or []}
        eligible = {q['id'] for q in source['questions'] if q['id'] in grades and grades[q['id']]['score'] < q['marks']}
        selected = set(map(str, body.question_ids))
        if not selected <= eligible:
            raise AppError('ASSESSMENT_PRACTICE_INVALID', 'Choose incorrect or partially correct questions from these results.', 422)
        if session.scalar(select(func.count()).select_from(assessments).where(assessments.c.learner_id==owner)) >= 200:
            raise AppError('ASSESSMENT_CAPACITY', 'Assessment capacity reached. Your saved results are preserved.', 409)
        questions, item_ids = [], {}
        ancestors = source.get('practice_lineage') or {}
        for original in source['questions']:
            if original['id'] not in selected: continue
            question = deepcopy(original)
            question['id'] = str(uuid4())
            questions.append(question)
            item_ids[question['id']] = ancestors.get('question_items', {}).get(original['id'], f"{source['id']}:{original['id']}")
        # Complete public paper references preserve passages, instructions and cross-part
        # dependencies, without leaking private keys or making reference parts answerable.
        public_source = repository.public(source)
        paper = source.get('paper')
        instructions = '\n\n'.join([paper.get('instructions', ''), *[
            f"{section['title']}: {section.get('instructions', '')}" for section in paper.get('sections', [])]]) if paper else ancestors.get('instructions', '')
        references = [q.model_dump(mode='json') for q in public_source.questions] if paper else ancestors.get('reference_questions', [])
        row = dict(id=str(uuid4()), learner_id=owner, context_id=source['context_id'],
            title=f"Practise mistakes · {source['title']}"[:200], purpose='practice', revision=1,
            created_at=repository.clock(), questions=questions, sources=deepcopy(source['sources']), paper=None,
            preferences=deepcopy(source.get('preferences') or {}), operation_id=str(body.client_request_id), fingerprint=fingerprint,
            practice_lineage=dict(assessment_id=source['id'], attempt_id=identifier, grade_revision=attempt['grade_revision'],
                known_exposure=True, question_items=item_ids, instructions=instructions, reference_questions=references))
        session.execute(assessments.insert().values(**row))
        session.execute(practice_operations.insert().values(learner_id=owner, operation_id=str(body.client_request_id),
            assessment_id=row['id'], fingerprint=fingerprint, created_at=row['created_at']))
        return repository.public(row)
