"""Owner-locked item quarantine, evidence withdrawal and private correction history."""
from copy import deepcopy
from sqlalchemy import select, update
from app.core.exceptions import AppError
from app.history_management.repositories.events.postgres import request_hash
from .tables import assessments, attempts, chat_drafts, item_reviews
from ..schemas import GeneratedQuestion
from ..quality import stored_question


def review_item(repository,owner,identifier,question_id,expected_revision,operation_id,reason,*,correction=None):
    if reason not in ('wrong_answer','ambiguous','answer_leak','trusted_correction'):
        raise AppError('ASSESSMENT_REVIEW_REASON','Choose a supported review reason.',422)
    if correction is not None:
        correction=GeneratedQuestion.model_validate(correction)
    fingerprint=request_hash(dict(assessment_id=identifier,question_id=question_id,reason=reason,
        correction=correction.model_dump(mode='json') if correction else None))
    with repository.transactions.write(owner) as tx:
        session=tx._session
        assessment=repository._assessment(session,owner,identifier)
        previous=session.execute(select(item_reviews).where(item_reviews.c.id==operation_id,
            item_reviews.c.learner_id==owner)).mappings().first()
        if previous:
            if previous['fingerprint']!=fingerprint: raise AppError('OPERATION_CONFLICT','Review request changed.',409)
            return repository.public(assessment)
        if assessment['revision']!=expected_revision: raise AppError('REVISION_CONFLICT','The assessment changed. Refresh before reviewing it.',409)
        questions=deepcopy(assessment['questions'])
        original=next((q for q in questions if q['id']==question_id),None)
        if original is None: raise AppError('ASSESSMENT_QUESTION_NOT_FOUND','Question unavailable.',404)
        before=deepcopy(original)
        if correction:
            if set(correction.concept_ids)!=set(original['concept_ids']):
                raise AppError('ASSESSMENT_REVIEW_TARGET','Corrections must retain original learning identities.',409)
            replacement=stored_question(correction,question_id)
            replacement['validation']['semantic_review']='trusted_correction'
            questions[questions.index(original)]=replacement
        else:
            original['validation']=dict(original.get('validation') or {},state='invalidated')
        session.execute(item_reviews.insert().values(id=operation_id,learner_id=owner,assessment_id=identifier,
            question_id=question_id,revision=assessment['revision']+1,reason=reason,
            decision='corrected' if correction else 'invalidated',previous_question=before,
            fingerprint=fingerprint,created_at=repository.clock()))
        session.execute(update(assessments).where(assessments.c.id==identifier,assessments.c.learner_id==owner)
            .values(questions=questions,revision=assessment['revision']+1))
        # Saved chat copies must show the same quarantine/correction. Existing
        # client submissions are fenced by the canonical assessment regardless.
        for draft in session.execute(select(chat_drafts).where(chat_drafts.c.learner_id==owner,
                chat_drafts.c.assessment_id==identifier)).mappings():
            payload=dict(draft['payload'],questions=questions,revision=assessment['revision']+1)
            session.execute(update(chat_drafts).where(chat_drafts.c.id==draft['id']).values(payload=payload))
        rows=session.execute(select(attempts).where(attempts.c.learner_id==owner,attempts.c.assessment_id==identifier)).mappings().all()
        for row in rows:
            affected=[receipt['evidence_id'] for receipt in row['evidence_receipt'] or []
                if receipt.get('question_id')==question_id and receipt.get('accepted')]
            if affected:
                if repository.withdraw_item_evidence is None: raise RuntimeError('Evidence withdrawal service unavailable')
                repository.withdraw_item_evidence(owner,affected,row['id'],tx)
            values=dict(revision=row['revision']+1,claim_id=None,claim_until=None,retry_at=None,
                evidence_status='unavailable',grading_progress={})
            if affected:
                values['evidence_receipt']=[dict(receipt,accepted=False,quality_withdrawn=True)
                    if receipt.get('question_id')==question_id else receipt for receipt in row['evidence_receipt'] or []]
            if correction and row['submission_id']:
                history=[*row['grade_history'],dict(grade_revision=row['grade_revision'],grades=row['grades'] or [],
                    answers=row['answers'],assistance=row['assistance'],reported_assistance=row['reported_assistance'],
                    scoring=row['scoring'],corrected_at=repository.clock().isoformat())]
                values.update(grade_history=history,grade_revision=row['grade_revision']+1,state='submitted',
                    grades=None,scoring=None,worker_attempts=0,evidence_status='pending',error=None)
            elif row['state'] in ('submitted','grading','failed'):
                values.update(state='failed',error='A question needs review. Your saved answers are preserved.')
            session.execute(update(attempts).where(attempts.c.id==row['id'],attempts.c.learner_id==owner).values(**values))
        if correction is None:
            root=(assessment.get('practice_lineage') or {}).get('question_items',{}).get(question_id,f'{identifier}:{question_id}')
            quarantine_derivatives(repository,tx,owner,identifier,root,operation_id,reason)
        return repository.public(dict(assessment,questions=questions,revision=assessment['revision']+1))


def quarantine_derivatives(repository,tx,owner,source_id,root,operation_id,reason):
    """Exposed/copy lineage cannot keep scoring an invalidated source key."""
    from uuid import UUID, uuid5
    session=tx._session
    for saved in session.execute(select(assessments).where(assessments.c.learner_id==owner,
            assessments.c.id!=source_id)).mappings().all():
        lineage=(saved.get('practice_lineage') or {}).get('question_items',{})
        ids={qid for qid,item in lineage.items() if item==root}
        ids.update(q['id'] for q in saved['questions'] if f"{saved['id']}:{q['id']}"==root)
        if not ids: continue
        questions=deepcopy(saved['questions'])
        for question in questions:
            if question['id'] not in ids: continue
            session.execute(item_reviews.insert().values(id=str(uuid5(UUID(operation_id),question['id'])),
                learner_id=owner,assessment_id=saved['id'],question_id=question['id'],revision=saved['revision']+1,
                reason=reason,decision='invalidated',previous_question=deepcopy(question),
                fingerprint=request_hash(dict(source_review=operation_id,root=root)),created_at=repository.clock()))
            question['validation']=dict(question.get('validation') or {},state='invalidated')
        session.execute(update(assessments).where(assessments.c.id==saved['id'],assessments.c.learner_id==owner)
            .values(questions=questions,revision=saved['revision']+1))
        for draft in session.execute(select(chat_drafts).where(chat_drafts.c.learner_id==owner,chat_drafts.c.assessment_id==saved['id'])).mappings().all():
            session.execute(update(chat_drafts).where(chat_drafts.c.id==draft['id']).values(payload=dict(draft['payload'],
                questions=questions,revision=saved['revision']+1)))
        for attempt in session.execute(select(attempts).where(attempts.c.learner_id==owner,attempts.c.assessment_id==saved['id'])).mappings().all():
            affected=[r['evidence_id'] for r in attempt['evidence_receipt'] or [] if r.get('question_id') in ids and r.get('accepted')]
            if affected:
                if repository.withdraw_item_evidence is None: raise RuntimeError('Evidence withdrawal service unavailable')
                repository.withdraw_item_evidence(owner,affected,attempt['id'],tx)
            values=dict(revision=attempt['revision']+1,evidence_status='unavailable',claim_id=None,claim_until=None,
                retry_at=None,grading_progress={},evidence_receipt=[dict(r,accepted=False,quality_withdrawn=True)
                    if r.get('question_id') in ids else r for r in attempt['evidence_receipt'] or []])
            if attempt['state'] in ('submitted','grading','failed'):
                values.update(state='failed',error='A source question needs review. Your saved answers are preserved.')
            session.execute(update(attempts).where(attempts.c.id==attempt['id'],attempts.c.learner_id==owner).values(**values))
