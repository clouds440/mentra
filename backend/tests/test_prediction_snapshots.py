"""Temporal records survive retries/corrections without ever exposing keys."""
import unittest
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select,update,event
from app.assessments.repositories.tables import prediction_snapshots,attempts
from app.assessments.repositories.predictions import content_hash
from app.assessments.schemas import StartAttempt
from app.core.exceptions import AppError
from tests import test_assessments as fixtures

class PredictionSnapshotTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.AssessmentTests.setUp

    async def test_capture_is_pre_outcome_private_immutable_and_exposure_fenced(self):
        assessment=await self.service.generate(self.owner,self.request)
        operation=StartAttempt(client_request_id=uuid4())
        queries=[]
        def observe(conn,cursor,statement,parameters,context,many):queries.append(statement)
        engine=self.db.sessions.kw['bind'];event.listen(engine,'before_cursor_execute',observe)
        try:first=self.service.repository.start(self.owner,str(assessment.id),operation)
        finally:event.remove(engine,'before_cursor_execute',observe)
        self.assertEqual(sum('FROM learner_concept_state' in sql for sql in queries),1)
        self.assertFalse(any('learning_evidence' in sql for sql in queries))
        def rows():
            with self.db.sessions() as session:return [dict(row) for row in session.execute(select(prediction_snapshots).where(prediction_snapshots.c.attempt_id==str(first.id))).mappings()]
        before=rows();self.assertEqual(len(before),2)
        from sqlalchemy.exc import DBAPIError
        with self.assertRaises(DBAPIError):
            with self.db.sessions.begin() as session:
                session.execute(update(prediction_snapshots).where(prediction_snapshots.c.attempt_id==str(first.id)).values(expected_score=.99))
        self.assertTrue(all(row['first_exposure'] and not row['supported'] for row in before))
        self.assertNotIn('model_answer',str(before));self.assertNotIn('prediction',str(self.service.repository.handoff(self.owner,str(assessment.id))))
        self.assertEqual(first.id,self.service.repository.start(self.owner,str(assessment.id),operation).id)
        with self.db.sessions.begin() as session:
            session.execute(update(attempts).where(attempts.c.id==str(first.id)).values(state='graded',grades=[],revision=2,submitted_at=before[0]['captured_at']+timedelta(seconds=1)))
        self.assertEqual(rows(),before)
        other=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        with self.db.sessions() as session:
            self.assertFalse(any(session.scalars(select(prediction_snapshots.c.first_exposure).where(prediction_snapshots.c.attempt_id==str(other.id)))))
        with self.assertRaises(AppError):self.service.repository.start(self.other,str(assessment.id),StartAttempt(client_request_id=uuid4()))

    async def test_supported_current_state_is_frozen_and_future_or_stale_state_abstains(self):
        from datetime import datetime,timezone
        from dataclasses import replace
        from app.learner.models import LearnerConceptState
        assessment=await self.service.generate(self.owner,self.request);skill=assessment.questions[0].concept_ids[0]
        now=datetime.now(timezone.utc)
        data=dict(ranking_half_life=30,policy_identity=self.learner.mastery_policy.identity,independent_items=['1','2','3'])
        for band in ('easy','medium','hard'):data.update({f'{band}_weight':3,f'{band}_success':3,f'{band}_items':['1','2','3'],f'{band}_last_at':now.isoformat()})
        state=LearnerConceptState(self.owner,skill,version=1,last_evidence_at=now,policy_data=data,
            mastery_policy_version=self.learner.mastery_policy.version,retention_policy_version=self.learner.retention_policy.version)
        with self.db.repository.transaction(learner_ids=[self.owner]) as repo:repo.save_state(state)
        first=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        def value(identifier):
            with self.db.sessions() as session:return dict(session.execute(select(prediction_snapshots).where(prediction_snapshots.c.attempt_id==str(identifier),prediction_snapshots.c.question_id==str(assessment.questions[0].id))).mappings().one())
        before=value(first.id);self.assertTrue(before['supported']);self.assertAlmostEqual(before['expected_score'],.875,places=4)
        with self.db.repository.transaction(learner_ids=[self.owner]) as repo:repo.save_state(replace(state,version=2,last_evidence_at=now+timedelta(days=1)))
        second=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        self.assertFalse(value(second.id)['supported']);self.assertEqual(value(first.id),before)
        with self.db.repository.transaction(learner_ids=[self.owner]) as repo:repo.save_state(replace(state,version=3,mastery_policy_version='unverified-policy'))
        third=self.service.repository.start(self.owner,str(assessment.id),StartAttempt(client_request_id=uuid4()))
        self.assertFalse(value(third.id)['supported'])

    def test_exact_copy_hash_ignores_generated_ids_case_spacing_and_option_order(self):
        q=dict(prompt='Force  / Mass',options=[dict(id='a',label='One'),dict(id='b',label='Two')])
        copy=dict(prompt='FORCE / MASS',options=[dict(id='z',label='two'),dict(id='x',label='one')])
        self.assertEqual(content_hash(q),content_hash(copy))
