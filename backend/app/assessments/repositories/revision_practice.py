"""Owner-scoped mistake history and durable, server-owned revision provenance."""
from copy import deepcopy
from random import SystemRandom
from uuid import uuid4
from sqlalchemy import select, func
from app.core.exceptions import AppError
from app.history_management.repositories.events.postgres import request_hash
from app.assessments.schemas import GenerationRequest, PaperSection, PlannedQuestion, PlannedPart
from .tables import assessments, attempts, generation_jobs


def collect(session, owner):
    graded_ids = select(attempts.c.assessment_id).where(attempts.c.learner_id == owner, attempts.c.state == 'graded')
    sources = {row['id']: dict(row) for row in session.execute(select(assessments).where(
        assessments.c.learner_id == owner, assessments.c.id.in_(graded_ids))).mappings()}
    # Read submitted answers, but never uploaded artifacts or grading checkpoints.
    results = session.execute(select(attempts.c.id, attempts.c.assessment_id, attempts.c.grades, attempts.c.answers,
        attempts.c.grade_revision, attempts.c.submitted_at, attempts.c.created_at).where(
        attempts.c.learner_id == owner, attempts.c.state == 'graded').order_by(
        attempts.c.submitted_at, attempts.c.created_at, attempts.c.id).execution_options(yield_per=100)).mappings()
    history, latest, failures = {}, {}, {}
    for result in results:
        source = sources.get(result['assessment_id'])
        if not source: continue
        lineage = source.get('practice_lineage') or {}
        questions = {q['id']: q for q in source['questions']}
        for grade in result['grades'] or []:
            question = questions.get(grade['question_id'])
            if not question: continue
            root = lineage.get('question_items', {}).get(question['id'], f"{source['id']}:{question['id']}")
            wrong = grade['score'] < question['marks']
            latest[root] = not wrong
            key = f"{source['id']}:{question['id']}"
            if not wrong: continue
            failures[root] = failures.get(root, 0) + 1
            previous = history.get(key)
            if wrong:
                history[key] = dict(id=key, _root_id=root, assessment_id=source['id'], assessment_title=source['title'],
                    attempt_id=result['id'], grade_revision=result['grade_revision'], question_id=question['id'],
                    prompt=question['prompt'], context=question.get('context', ''), topic_ids=question['concept_ids'],
                    score=grade['score'], marks=question['marks'], feedback=grade['feedback'],
                    answer=(result['answers'] or {}).get(question['id'], ''),
                    answer_mode=question.get('answer_mode'), options=deepcopy(question.get('options') or []),
                    occurrences=(previous['occurrences'] if previous else 0)+1, resolved=False,
                    occurred_at=(result['submitted_at'] or result['created_at']).isoformat(),
                    _question=deepcopy(question), _context_id=lineage.get('question_contexts', {}).get(question['id'], source['context_id']))
    from app.learner.repositories.tables.concepts import concept
    ids = {identifier for item in history.values() for identifier in item['topic_ids']}
    names = dict(session.execute(select(concept.c.id, concept.c.canonical_name).where(concept.c.id.in_(ids))).all()) if ids else {}
    items = list(history.values())
    for item in items:
        item['resolved'] = latest[item['_root_id']]
        item['occurrences'] = failures[item['_root_id']]
        item['topics'] = [dict(id=identifier, name=names.get(identifier, 'Learning topic')) for identifier in item['topic_ids']]
        item['priority'] = 'Repeated mistake' if item['occurrences'] > 1 else 'Incorrect answer' if item['score'] == 0 else 'Partial answer'
    items.sort(key=lambda x: (not x['resolved'], x['occurrences'], 1-x['score']/x['marks'], x['marks'], x['occurred_at']), reverse=True)
    return items


def matches(item, assessment_ids, topic_ids):
    return (not assessment_ids or item['assessment_id'] in assessment_ids) and (not topic_ids or bool(set(item['topic_ids']) & set(topic_ids)))


def list_mistakes(repository, owner, assessment_ids=(), topic_ids=(), offset=0):
    from .mistake_view import page
    return page(repository, owner, assessment_ids, topic_ids, offset)


def enqueue_revision(service, owner, body):
    repository = service.repository
    fingerprint = request_hash(dict(kind='revision-practice-v1', assessment_ids=sorted(set(map(str, body.assessment_ids))),
        topic_ids=sorted(set(body.topic_ids)), count=body.count))
    with repository.transactions.write(owner) as tx:
        session = tx._session
        previous = session.execute(select(generation_jobs).where(generation_jobs.c.learner_id == owner,
            generation_jobs.c.operation_id == str(body.client_request_id))).mappings().first()
        if previous:
            if previous['fingerprint'] != fingerprint: raise AppError('OPERATION_CONFLICT', 'This request ID belongs to different practice.', 409)
            return service.generation_jobs.public(previous)
        selected_ids = set(map(str, body.assessment_ids))
        if selected_ids:
            owned = set(session.scalars(select(assessments.c.id).where(assessments.c.learner_id == owner, assessments.c.id.in_(selected_ids))))
            if owned != selected_ids: raise AppError('ASSESSMENT_NOT_FOUND', 'One or more assessments are unavailable.', 404)
        eligible = [x for x in collect(session, owner) if not x['resolved'] and matches(x, selected_ids, body.topic_ids)]
        unique = {}
        for item in eligible: unique.setdefault(item['_root_id'], item)
        chosen = list(unique.values())[:body.count]
        if not chosen: raise AppError('NO_PRACTICE_MISTAKES', 'No unresolved mistakes match these filters.', 422)
        if session.scalar(select(func.count()).select_from(generation_jobs).where(generation_jobs.c.learner_id == owner,
                generation_jobs.c.state.in_(['queued', 'running']))) >= 2:
            raise AppError('ASSESSMENT_GENERATION_BUSY', 'Let your current assessments finish first.', 409)
        # Shuffle once; retries use this immutable snapshot, not a new selection.
        SystemRandom().shuffle(chosen)
        questions = [x['_question'] for x in chosen]
        sections = [PaperSection(title='Revision practice', question_count=len(chosen), questions=[
            PlannedQuestion(number=i+1, parts=[PlannedPart(question_type=q.get('question_type') or 'written',
                answer_mode=q.get('answer_mode') or 'text', marks=q['marks'],
                brief='Create a fresh self-contained variation of original question at this position. Preserve its learning target. '
                    'Change wording and examples or values; shuffle choices where applicable. Put all necessary context in the new prompt. '
                    'Original context: '+q.get('context', '')+'\nFeedback to address: '+item['feedback'])])
            for i, (q, item) in enumerate(zip(questions, chosen))])]
        request = GenerationRequest(client_request_id=body.client_request_id, context_id=chosen[0]['_context_id'],
            topic='Revision assessment', count=len(chosen), question_format='mixed', paper_sections=sections,
            instructions='Create new variations of these mistakes in the supplied shuffled order, not copies. Keep one answerable question per original. '
                'Make each question self-contained even if the original belonged to a multipart paper. Do not reveal answers in prompts.',
            result_style='marks')
        public_questions = [{key: value for key, value in q.items() if key not in ('model_answer','rubric','correct_option_id','correct_option_ids','concept_names')} for q in questions]
        snapshot = dict(questions=public_questions, source_assessment_ids=list(dict.fromkeys(x['assessment_id'] for x in chosen)),
            sources=[dict(assessment_id=x['assessment_id'], attempt_id=x['attempt_id'], question_id=x['question_id'],
                grade_revision=x['grade_revision'], root_id=x['_root_id'], context_id=x['_context_id']) for x in chosen])
        row = dict(id=str(uuid4()), learner_id=owner, operation_id=str(body.client_request_id), fingerprint=fingerprint,
            conversation_id=None, request=request.model_dump(mode='json'), state='queued',
            progress=dict(mistake_revision=snapshot, resolved_request=request.model_dump(mode='json')),
            result=None, error=None, attempts=0, claim_id=None, claim_until=None, created_at=repository.clock())
        session.execute(generation_jobs.insert().values(**row))
        return service.generation_jobs.public(row)


def revision_lineage(snapshot, questions):
    if len(questions) != len(snapshot['sources']): raise AppError('ASSESSMENT_INVALID_GENERATION', 'Revision question count changed.', 422)
    first = snapshot['sources'][0]
    return dict(assessment_id=first['assessment_id'], attempt_id=first['attempt_id'], grade_revision=first['grade_revision'],
        known_exposure=True, instructions='', reference_questions=[], revision_assessment=True,
        source_assessment_ids=snapshot['source_assessment_ids'], source_questions=snapshot['sources'],
        question_sources={q['id']: source for q, source in zip(questions, snapshot['sources'])},
        question_items={q['id']: source['root_id'] for q, source in zip(questions, snapshot['sources'])},
        question_contexts={q['id']: source['context_id'] for q, source in zip(questions, snapshot['sources'])})
