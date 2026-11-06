import unittest
from unittest.mock import patch
from sqlalchemy import delete,select,event
from app.learner.repositories.tables.projections import ranking_projection
from app.learner.schemas import StudyRecommendationsRequest
from app.learner.engine import LearnerEngine
from tests import test_ranking_projection as fixtures

class ProjectionRecoveryTests(unittest.TestCase):
    setUp=fixtures.RankingIndexTests.setUp
    seed=fixtures.RankingIndexTests.seed

    def test_rebuild_restores_ranking_without_changing_beliefs_or_reading_ledger(self):
        self.seed(5);before=self.db.repository.list_states(self.owner)
        expected=self.engine.get_study_targets(self.owner,[self.context])
        with self.db.sessions.begin() as session:session.execute(delete(ranking_projection).where(ranking_projection.c.learner_id==self.owner))
        queries=[]
        def observe(conn,cursor,statement,parameters,context,many):queries.append(statement)
        event.listen(self.db.engine,'before_cursor_execute',observe)
        try:
            first=self.db.repository.rebuild_ranking_projection(self.owner,limit=2)
            second=self.db.repository.rebuild_ranking_projection(self.owner,first['next_cursor'],limit=2)
            third=self.db.repository.rebuild_ranking_projection(self.owner,second['next_cursor'],limit=2)
        finally:event.remove(self.db.engine,'before_cursor_execute',observe)
        self.assertEqual(first['rebuilt']+second['rebuilt']+third['rebuilt'],5);self.assertIsNone(third['next_cursor'])
        self.assertEqual(before,self.db.repository.list_states(self.owner))
        self.assertFalse(any('learning_evidence' in sql for sql in queries))
        self.assertEqual(expected,self.engine.get_study_targets(self.owner,[self.context]))
        from testing.identities import learner_id
        self.assertEqual(self.db.repository.rebuild_ranking_projection(learner_id('bob'))['rebuilt'],0)

    def test_recent_due_plan_b_is_bounded_and_makes_no_verification_claim(self):
        self.seed(5)
        with patch('app.core.config.settings.learner_ranking_mode','recent_due'):
            engine=LearnerEngine(self.db.repository,clock=lambda:self.now)
        result=engine.get_study_targets(self.owner,[self.context])
        self.assertEqual(result['verification'],[])
        self.assertTrue(result['recommendations'])
        self.assertEqual({row.reason for row in result['recommendations']},{'recent_due_practice'})
