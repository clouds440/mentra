import os
import random
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from app.learner.models import LearnerConceptState
from app.learner.scoring.projection import project,expected
from app.learner.scoring.signals import performance_estimate


class ProjectionMathTests(unittest.TestCase):
    def test_exact_equivalence_across_bands_histories_ages_and_half_lives(self):
        rng=random.Random(406)
        anchor=datetime(2026,1,1,tzinfo=timezone.utc)
        for iteration in range(300):
            data={}
            for band in ('easy','medium','hard'):
                rows=[dict(at=(anchor-timedelta(days=rng.random()*300)).isoformat(),
                    weight=rng.random(),outcome=rng.random()) for _ in range(rng.randrange(1,65))]
                data.update({f'{band}_weight':sum(r['weight'] for r in rows),
                    f'{band}_success':sum(r['weight']*r['outcome'] for r in rows),
                    f'{band}_items':list(range(len(rows))),f'{band}_recall_times':list(range(rng.randrange(33))),
                    f'{band}_last_at':max(r['at'] for r in rows)})
                if iteration%2:
                    data[f'{band}_observations']=rows
            state=LearnerConceptState('owner','skill',last_evidence_at=anchor,policy_data=data)
            half_life=rng.uniform(.1,180)
            indexed=project(state,half_life)
            for difficulty in (.2,.5,.8):
                for age in (0,1,30,365,3650):
                    now=anchor+timedelta(days=age)
                    mean,_,_,supported,_=performance_estimate(state,difficulty,now,half_life)
                    scalar,scalar_supported=expected(indexed,difficulty,now)
                    self.assertEqual(supported,scalar_supported)
                    self.assertAlmostEqual(mean,scalar,places=13)
            with self.assertRaises(ValueError): expected(indexed,.5,anchor-timedelta(seconds=1))


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Requires disposable database')
class RankingIndexTests(unittest.TestCase):
    def setUp(self):
        from testing.postgres import PostgresSandbox
        from testing.identities import learner_id
        from app.learner import LearnerEngine
        from app.learner.schemas import ResolveLearningContextRequest
        self.db=PostgresSandbox();self.addCleanup(self.db.close)
        self.owner=learner_id('alice'); self.now=datetime(2026,11,6,tzinfo=timezone.utc)
        self.engine=LearnerEngine(self.db.repository,clock=lambda:self.now)
        self.context=self.engine.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner,name='Projection checks')).context_id

    def seed(self,count=350):
        from app.learner.scoring import HeuristicMasteryPolicy
        rng=random.Random(121)
        ids=[]
        with self.db.repository.transaction(learner_ids=[self.owner]) as repo:
            for i in range(count):
                from app.learner.models import Concept
                skill=Concept(f'projection-{i}',f'Skill {i}')
                repo.create_concept(skill)
                repo.add_context_concept(self.context,skill.id,learner_id=self.owner)
                data=dict(policy_identity=self.engine.mastery_policy.identity,ranking_half_life=30,
                    independent_items=list(range(6)))
                for band in ('easy','medium','hard'):
                    data.update({f'{band}_weight':3,f'{band}_success':rng.random()*3,
                        f'{band}_items':[1,2,3],f'{band}_last_at':(self.now-timedelta(days=rng.randrange(100))).isoformat()})
                state=LearnerConceptState(self.owner,skill.id,mastery=rng.random(),estimate_confidence=rng.random(),
                    retention_confidence=rng.random(),last_evidence_at=self.now-timedelta(days=1),
                    last_demonstrated_at=self.now-timedelta(days=rng.randrange(200)),version=1,policy_data=data,
                    mastery_policy_version=self.engine.mastery_policy.version,retention_policy_version=self.engine.retention_policy.version,
                    verification_required=i%23==0)
                repo.save_state(state);ids.append(skill.id)
        return ids

    def test_shortlist_matches_full_scan_and_is_bounded(self):
        ids=self.seed()
        for supported in (False,True):
            for age in (0,90,1000):
                self.now+=timedelta(days=age)
                actual=self.engine.get_study_targets(self.owner,[self.context],supported_verification=supported)
                from app.learner.schemas import StudyRecommendationsRequest
                request=StudyRecommendationsRequest(learner_id=self.owner,context_ids=[self.context])
                contexts=self.engine.contexts.select(self.owner,[self.context])
                data=(self.db.repository.context_concepts(self.owner,[self.context]),self.engine.states.load(self.owner,ids),
                    self.db.repository.prerequisite_counts(ids,[self.context],self.owner),
                    self.db.repository.context_factors(self.owner,contexts),self.now)
                oracle=dict(recommendations=self.engine.retrieval.recommend(request,data=data),
                    verification=self.engine.retrieval.recommend(request,verification=True,data=data,supported_only=supported))
                for mode in actual:
                    self.assertEqual([(v.concept_id,round(v.priority,12)) for v in actual[mode]],
                        [(v.concept_id,round(v.priority,12)) for v in oracle[mode]],(supported,age,mode))
        contexts=self.engine.contexts.select(self.owner,[self.context])
        shortlist=self.db.repository.ranking_candidates(self.owner,contexts,self.now,self.engine.mastery_policy,
            self.engine.retention_policy,self.engine.retrieval.ranking)
        self.assertLessEqual(len(shortlist),256)

    def test_state_and_projection_rollback_together(self):
        from sqlalchemy import select,func
        from app.learner.repositories.tables.projections import ranking_projection
        self.seed(1)
        original=self.db.repository.get_state(self.owner,'projection-0')
        with self.assertRaisesRegex(RuntimeError,'rollback'):
            with self.db.repository.transaction(learner_ids=[self.owner]) as repo:
                repo.save_state(replace(original,version=2,mastery=.1))
                raise RuntimeError('rollback')
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(ranking_projection.c.state_version)),1)
        self.assertEqual(self.db.repository.get_state(self.owner,'projection-0').version,1)

    def test_context_difficulty_importance_and_grouping_preserve_oracle(self):
        from sqlalchemy import insert,update,case
        from app.learner.repositories.tables.topics import learning_topic,topic_skill
        from app.learner.repositories.tables import context_concept
        from app.learner.schemas import StudyRecommendationsRequest
        ids=self.seed()
        with self.db.sessions.begin() as session:
            session.execute(insert(learning_topic).values(id='large-topic',learner_id=self.owner,context_id=self.context,
                name='Large topic',normalized_name='large topic',scope='Fixture',scope_key='fixture'))
            session.execute(insert(topic_skill),[dict(learner_id=self.owner,concept_id=key,topic_id='large-topic',
                label=key,ability=key,published=True,resolver_version='test') for key in ids[:300]])
            session.execute(update(context_concept).where(context_concept.c.concept_id.in_(ids[:200])).values(target_difficulty=.8,importance=.8))
            session.execute(update(context_concept).where(context_concept.c.concept_id.in_(ids[200:250])).values(target_difficulty=.2,importance=0))
        request=StudyRecommendationsRequest(learner_id=self.owner,context_ids=[self.context])
        contexts=self.engine.contexts.select(self.owner,[self.context])
        data=(self.db.repository.context_concepts(self.owner,[self.context]),self.engine.states.load(self.owner,ids),{},
            self.db.repository.context_factors(self.owner,contexts),self.now)
        actual=self.engine.get_study_targets(self.owner,[self.context],supported_verification=True)
        for mode in actual:
            oracle=self.engine.retrieval.recommend(request,data=data,verification=mode=='verification',supported_only=mode=='verification')
            self.assertEqual([v.concept_id for v in actual[mode]],[v.concept_id for v in oracle])
            self.assertLessEqual(sum(v.topic_id=='large-topic' for v in actual[mode]),1)
