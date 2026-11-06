import unittest
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select,insert,update,func
from app.core.exceptions import AppError
from app.learner.schemas import ResolveLearningContextRequest
from app.learner.repositories.tables import concept,learning_evidence,learner_concept_state,learner_audit
from app.learner.repositories.tables.signals import learning_signals
from app.learner.repositories.tables.topics import topic_skill
from tests import test_learning_signals as fixtures


class SignalReviewTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.SignalCaptureTests.setUp
    turn=fixtures.SignalCaptureTests.turn

    async def test_source_review_converges_without_mastery_and_pending_stays_out(self):
        self.turn();await self.worker.run_once()
        context=self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner,name='Calculus')).context_id
        skill=self.learner.register_concept('Chain rule')
        self.learner.link_context_concept(self.owner,context,skill.id)
        row=self.learner.get_learning_signals(self.owner)['items'][0]
        with self.db.sessions.begin() as session:
            session.execute(update(learning_signals).values(status='pending'))
        self.assertEqual(self.learner.get_assessment_context(self.owner,context,'Chain rule').packet.observations,[])
        with self.db.sessions.begin() as session:
            values=[]
            for i in range(1000):
                values.append(dict(row,id=str(uuid4()),label=f'Chain rule paraphrase {i}',fingerprint=f'review-{i}'))
            session.execute(insert(learning_signals),values)
        for value in values:
            result=self.learner.review_learning_signal(self.owner,value['id'],context,skill.id,row['source_revision'])
            self.assertEqual(result['concept_id'],skill.id)
        packet=self.learner.get_assessment_context(self.owner,context,'Chain rule').packet
        self.assertTrue(packet.observations)
        self.assertLessEqual(len(packet.observations),8)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(concept)),1)
            self.assertEqual(session.scalar(select(func.count()).select_from(learning_evidence)),0)
            self.assertEqual(session.scalar(select(func.count()).select_from(learner_concept_state)),0)
        with self.assertRaises(AppError):
            self.learner.review_learning_signal(self.other,row['id'],context,skill.id,row['source_revision'])
        with self.assertRaises(AppError):
            self.learner.review_learning_signal(self.owner,row['id'],context,skill.id,'stale-source')
        self.learner.withdraw_learning_signal(self.owner,row['id'])
        with self.assertRaises(AppError):
            self.learner.review_learning_signal(self.owner,row['id'],context,skill.id,row['source_revision'])

    async def test_cleanup_rechecks_publication_and_protects_nested_source_references(self):
        from app.learner.models import Concept
        from datetime import datetime,timezone
        ids=[str(uuid4()) for _ in range(3)]
        with self.db.repository.transaction(learner_ids=[self.owner],ontology=True) as repo:
            for i,identifier in enumerate(ids):
                repo.create_concept(Concept(identifier,f'unclassified-cleanup-{i}'))
                repo.save_ungrouped_skill(self.owner,identifier,f'Staged {i}')
            repo.audit('checkpoint_fixture',{'nested':[{'concept_ids':[ids[1]]}]},self.owner)
        with self.db.sessions.begin() as session:
            session.execute(update(topic_skill).values(created_at=datetime.now(timezone.utc)-timedelta(days=9)))
        preview=self.db.repository.cleanup_staged_skills(self.owner)
        self.assertEqual(set(preview['ids']),{ids[0],ids[2]})
        with self.db.repository.transaction(learner_ids=[self.owner]) as repo:
            repo.publish_topic_skills(self.owner,[ids[2]])
        with self.assertRaises(AppError):
            self.db.repository.cleanup_staged_skills(self.owner,apply=True,expected_digest=preview['digest'])
        preview=self.db.repository.cleanup_staged_skills(self.owner)
        self.assertEqual(preview['ids'],[ids[0]])
        applied=self.db.repository.cleanup_staged_skills(self.owner,apply=True,expected_digest=preview['digest'])
        self.assertEqual(applied['ids'],preview['ids'])
        self.assertIsNone(self.db.repository.get_concept(ids[0]))
        self.assertIsNotNone(self.db.repository.get_concept(ids[1]))
        self.assertIsNotNone(self.db.repository.get_concept(ids[2]))


class PromptBudgetTests(unittest.TestCase):
    def test_multilingual_packet_is_bounded_with_explicit_coverage(self):
        import json
        from app.learner.prompt_context import compact
        from app.learner.schemas import LearnerContextPacket,LearnerContextConcept
        packet=LearnerContextPacket(concepts=[LearnerContextConcept(concept_id=str(i),name='قاعدة السلسلة '*100)
            for i in range(50)],observations=[dict(id=str(i),kind='struggle',label='لدي صعوبة '*100,quote='مثال '*1000) for i in range(8)])
        result=compact(packet)
        self.assertLessEqual(len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()),2000)
        self.assertLessEqual(len(result['skills']),8)
        self.assertEqual(result['coverage']['skills_available'],50)
