import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.learner import LearnerEngine, LearningProgressRequest, ResolveLearningContextRequest, ConceptResolutionRequest
from app.learner.models import LearnerConceptState
from app.learner.exceptions import LearningContextNotFoundError
from app.learner.schemas import VerificationCandidatesRequest
from app.student_profile.dependencies import require_onboarded_identity
from app.api.routes.learning import router
from testing.postgres import PostgresSandbox
from testing.identities import learner_id


class LearningProgressTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox(); self.addCleanup(self.db.close)
        self.owner, self.other = learner_id('alice'), learner_id('bob')
        self.now = datetime.now(timezone.utc)
        self.learner = LearnerEngine(self.db.repository, clock=lambda:self.now)
        self.context = self.learner.resolve_learning_context(ResolveLearningContextRequest(
            learner_id=self.owner, name='AI basics', activate=True))

    def concept(self, name, aliases=()):
        concept = self.learner.register_concept(name, aliases=aliases)
        self.learner.link_context_concept(self.owner, self.context.context_id, concept.id)
        return concept

    def page(self, **options):
        return self.learner.get_learning_progress(LearningProgressRequest(learner_id=self.owner, **options))

    def test_full_collection_pagination_deduplicates_context_links_and_clamps_last_page(self):
        concepts = [self.concept(f'Topic {i:02}') for i in range(27)]
        extra = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.owner, name='Second area'))
        self.learner.link_context_concept(self.owner, extra.context_id, concepts[0].id)
        ids = [self.context.context_id, extra.context_id]
        pages = [self.page(context_ids=ids, offset=offset) for offset in (0,10,20,1000)]
        self.assertEqual([len(p.items) for p in pages], [10,10,7,7])
        self.assertEqual([p.offset for p in pages], [0,10,20,20])
        self.assertTrue(all(p.total == p.total_concepts == 27 for p in pages))
        self.assertEqual([x.name for p in pages[:3] for x in p.items], [f'Topic {i:02}' for i in range(27)])
        self.assertTrue(all(x.mastery is None for x in pages[0].items))

    def test_search_finds_alias_and_name_beyond_the_old_top_twelve(self):
        for i in range(16): self.concept(f'AI topic {i:02}', aliases=['Neural networks'] if i == 15 else [])
        by_name = self.page(query='  AI TOPIC 15 ')
        by_alias = self.page(query='NETW')
        self.assertEqual([x.name for x in by_name.items], ['AI topic 15'])
        self.assertEqual([x.name for x in by_alias.items], ['AI topic 15'])
        self.assertEqual((by_alias.total, by_alias.total_concepts), (1,16))
        empty = self.page(query="%' OR 1=1 --", offset=100)
        self.assertEqual((empty.items, empty.offset, empty.total, empty.total_concepts), ([],0,0,16))

    def test_pages_and_search_remain_owner_scoped(self):
        self.concept('Visible topic')
        other = self.learner.resolve_learning_context(ResolveLearningContextRequest(learner_id=self.other, name='Private area', activate=True))
        secret = self.learner.register_concept('Private topic')
        self.learner.link_context_concept(self.other, other.context_id, secret.id)
        self.assertEqual(self.page().total, 1)
        self.assertEqual(self.page(query='Private').total, 0)
        with self.assertRaises(LearningContextNotFoundError): self.page(context_ids=[other.context_id])

    def test_empty_page_and_pagination_boundaries(self):
        self.assertEqual((self.page().items, self.page().total), ([],0))
        for options in ({'limit':51}, {'limit':0}, {'offset':-1}, {'query':'x'*201}):
            with self.assertRaises(ValidationError): self.page(**options)

    def test_confirmation_accepts_topic_without_creating_mastery(self):
        candidate = self.learner.resolve_concept(ConceptResolutionRequest(learner_id=self.owner,
            context_id=self.context.context_id, label='Fine tuning'))
        concept = self.learner.review_owned_candidate(self.owner, candidate.candidate_id)
        self.assertEqual(self.learner.review_owned_candidate(self.owner, candidate.candidate_id).id, concept.id)
        self.assertEqual(self.page().total, 1)
        self.assertIsNone(self.page().items[0].mastery)
        self.assertIsNone(self.db.repository.get_state(self.owner, concept.id))

    def state(self, concept, confidence=.55, supported=True, conflict=False):
        data = dict(independent_items=['a','b','c'], mastery_band='medium', medium_weight=3,
            medium_capability=2, medium_items=['a','b','c'], medium_last_at=self.now.isoformat(),
            policy_identity=self.learner.mastery_policy.identity)
        if not supported: data['medium_items'] = ['a']
        self.db.repository.save_state(LearnerConceptState(learner_id=self.owner, concept_id=concept.id,
            mastery=.6, estimate_confidence=confidence, retention_confidence=.9,
            last_demonstrated_at=self.now, verification_required=conflict, policy_data=data, version=1,
            mastery_policy_version=self.learner.mastery_policy.version))

    def test_progress_hides_unsupported_review_without_breaking_ai_bootstrap(self):
        self.concept('No answers yet')
        unverified = self.concept('Only one difficulty observation'); self.state(unverified, supported=False)
        regular = self.concept('Needs a useful follow-up'); self.state(regular)
        known = self.concept('Well supported topic'); self.state(known, confidence=.9)
        targets = self.learner.get_study_targets(self.owner, limit=1, supported_verification=True)
        self.assertEqual([x.concept_id for x in targets['verification']], [regular.id])
        self.assertEqual(targets['verification'][0].reason, 'low_estimate_confidence')
        ai = self.learner.get_verification_candidates(VerificationCandidatesRequest(learner_id=self.owner))
        self.assertIn('insufficient_evidence', [x.reason for x in ai])
        self.assertIn('difficulty_unverified', [x.reason for x in ai])

    def test_real_mixed_answers_are_still_shown_for_review(self):
        concept = self.concept('Mixed results'); self.state(concept, confidence=.2, supported=False, conflict=True)
        suggestions = self.learner.get_study_targets(self.owner, supported_verification=True)['verification']
        self.assertEqual([x.reason for x in suggestions], ['contradictory_evidence'])

    def test_http_page_is_bounded_private_and_uses_the_public_facade(self):
        self.concept('AI training')
        app = FastAPI(); app.include_router(router, prefix='/api/v1'); app.state.learner_service = self.learner
        app.dependency_overrides[require_onboarded_identity] = lambda:SimpleNamespace(learner_id=self.owner)
        with TestClient(app) as client:
            response = client.get('/api/v1/learning/understanding?query=training&limit=10')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.json()['total'], 1)
            self.assertEqual(client.get('/api/v1/learning/understanding?limit=100').status_code, 422)
            self.assertEqual(client.get('/api/v1/learning').json()['verification'], [])
