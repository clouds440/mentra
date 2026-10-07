"""Real PostgreSQL scope, workflow, evidence, concurrency and migration checks."""
import asyncio
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import patch
from alembic import command
from sqlalchemy import select, func, update, delete, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.student_profile import StudentProfileService, ProfileDetails, ProfileUpdate, EvidenceInput, EvidenceItem
from app.student_profile.schemas import VersionRequest, AnswerRequest, DIMENSIONS, AIEvaluation, EducationLevel
from app.student_profile.repositories.postgres import PostgresStudentProfileRepository
from app.student_profile.repositories.tables import student_profile, calibration_attempt, profile_evidence
from app.student_profile.calibration.blueprints import blueprint, banks
from app.student_profile.calibration.domains import VARIANTS
from app.student_profile.errors import EvaluationUnavailable
from app.core.exceptions import AppError
from app.auth.repositories.postgres import PostgresIdentityRepository
from app.auth.service import AuthService
from app.auth.tokens import ExternalTokenVerifier
from app.api.router import api_router
from app.core.exception_handlers import register_exception_handlers
from app.db.migrate import upgrade, migration_config
from app.learner.repositories.tables import learner_concept_state, learning_evidence
from testing.identities import learner_id
from testing.postgres import PostgresSandbox
from testing.profile_evaluator import TestProfileEvaluator

A, B = learner_id('student-a'), learner_id('student-b')


def details(**changes):
    return ProfileDetails.model_validate(dict(education_level='primary', field_of_study='General studies',
        learning_goal='Understand the world around me', learning_preference='examples_first', explanation_depth='standard') | changes)


class StudentProfileTests(unittest.TestCase):
    def setUp(self):
        self.db = PostgresSandbox()
        self.addCleanup(self.db.close)
        self.evaluator = TestProfileEvaluator()
        self.repository = PostgresStudentProfileRepository(self.db.sessions)
        self.service = StudentProfileService(self.repository, self.evaluator)

    def fill_details(self, owner=A, **changes):
        values = details().model_dump() | changes
        return self.service.update_details(owner, ProfileUpdate(expected_version=self.service.get(owner).version, details=values))

    def answer_all(self, owner=A, *, correct=True):
        self.fill_details(owner)
        view = self.service.calibration.start(owner)
        with self.repository.transaction(owner) as store:
            private = store.attempt(view.id)
        for question in private.questions:
            option = question.correct_option_id if correct else next(option.id for option in question.options if option.id != question.correct_option_id)
            view = self.service.calibration.answer(owner, view.id, AnswerRequest(expected_version=view.version, question_id=question.id, option_id=option))
        return view

    def complete(self, owner=A, **changes):
        view = self.answer_all(owner, **changes)
        return asyncio.run(self.service.calibration.complete(owner, view.id, VersionRequest(expected_version=view.version)))

    def count(self, table):
        with self.db.engine.connect() as connection:
            return connection.execute(select(func.count()).select_from(table)).scalar_one()

    def test_mandatory_information_cannot_be_skipped_or_forged(self):
        initial = self.service.get(A)
        self.assertEqual(initial.onboarding_phase, 'information')
        self.assertTrue(all(getattr(initial.estimates, dimension).value is None for dimension in DIMENSIONS))
        for action in (lambda: self.service.calibration.start(A), lambda: self.service.calibration.skip(A, VersionRequest(expected_version=initial.version))):
            with self.assertRaises(AppError) as error:
                action()
            self.assertEqual(error.exception.code, 'PROFILE_INFORMATION_REQUIRED')
        for invalid in ({'education_level': 'doctoral_fake'}, {'field_of_study': ' '}, {'learning_goal': ''}):
            with self.assertRaises(ValidationError):
                ProfileDetails.model_validate(details().model_dump() | invalid)
        with self.assertRaises(ValidationError):
            ProfileUpdate(expected_version=1, details=details(), estimates={'reasoning': 1})
        profile = self.fill_details()
        self.assertEqual(profile.onboarding_phase, 'calibration')
        skipped = self.service.calibration.skip(A, VersionRequest(expected_version=profile.version))
        self.assertEqual(skipped.onboarding_phase, 'complete')
        self.assertEqual(skipped.calibration_status, 'skipped')
        self.assertEqual(skipped.estimates, initial.estimates)
        self.assertEqual(len(self.evaluator.calls), 0)

    def test_every_level_and_domain_has_valid_distinct_versioned_blueprints(self):
        prompt_sets = []
        for level in EducationLevel:
            profile_details = details().model_copy(update={'education_level': level})
            version, questions = blueprint(profile_details, 'stable-seed')
            self.assertIn(level.value, version)
            self.assertEqual(len(questions), 8)
            self.assertEqual(len({item.id for item in questions}), 8)
            self.assertTrue(all(item.correct_option_id in {option.id for option in item.options} for item in questions))
            self.assertTrue(all(len({option.text for option in item.options}) == len(item.options) for item in questions))
            prompt_sets.append({item.prompt for item in questions})
        for index, first in enumerate(prompt_sets):
            for second in prompt_sets[index + 1:]:
                self.assertFalse(first & second)
        for domain, levels in VARIANTS.items():
            field = {'computing': 'Computer science', 'health': 'Medicine', 'business': 'Business', 'humanities': 'History', 'stem': 'Physics'}[domain]
            for level in levels:
                version, questions = blueprint(ProfileDetails.model_validate(details().model_dump() | {'education_level': level, 'field_of_study': field}))
                self.assertTrue(version.endswith('/' + domain))
                self.assertEqual(len(questions), 8)
                self.assertTrue(all(item.dimension == 'domain_familiarity' for item in questions[-2:]))

    def test_draft_restores_answers_and_never_exposes_keys(self):
        self.fill_details()
        view = self.service.calibration.start(A)
        self.assertNotIn('correct_option_id', view.model_dump_json())
        self.assertNotIn('difficulty', view.model_dump_json())
        question = view.questions[0]
        updated = self.service.calibration.answer(A, view.id, AnswerRequest(expected_version=view.version, question_id=question.id, option_id=question.options[0].id))
        self.assertEqual(self.service.calibration.get(A), updated)
        self.assertEqual(self.service.calibration.start(A), updated)
        with self.assertRaises(AppError):
            self.service.calibration.answer(A, view.id, AnswerRequest(expected_version=updated.version, question_id=question.id, option_id='invented'))
        with self.assertRaises(AppError):
            asyncio.run(self.service.calibration.complete(A, view.id, VersionRequest(expected_version=updated.version)))
        self.assertEqual(self.count(profile_evidence), 0)

    def test_hybrid_evaluation_has_item_results_and_never_writes_learner_mastery(self):
        result = self.complete()
        self.assertEqual(result.profile.calibration_status, 'completed')
        self.assertEqual(result.profile.evaluation_status, 'applied')
        self.assertEqual(result.profile.details, details())
        evidence, context = self.evaluator.calls[0]
        self.assertEqual(len(evidence.input.items), 8)
        self.assertTrue(all(item.correct and item.prompt and item.difficulty is not None for item in evidence.input.items))
        self.assertEqual(context.details, details())
        self.assertEqual(self.count(learner_concept_state), 0)
        self.assertEqual(self.count(learning_evidence), 0)
        self.assertEqual(result.profile.estimates.reasoning.evidence_count, 2)
        self.assertLessEqual(result.profile.estimates.reasoning.confidence, .25)
        self.assertLessEqual(result.profile.estimates.overall_proficiency.confidence, .55)
        view = self.service.calibration.get(A)
        again = asyncio.run(self.service.calibration.complete(A, view.id, VersionRequest(expected_version=1)))
        self.assertEqual(again.profile, result.profile)
        self.assertEqual(self.count(profile_evidence), 1)
        self.assertEqual(len(self.evaluator.calls), 1)
        self.assertLess(len(self.service.prompt_context(A).model_dump_json()), 2000)

    def test_provider_failure_preserves_completed_evidence_for_retry(self):
        class Unavailable:
            async def evaluate(self, *_):
                raise EvaluationUnavailable()
        self.service.evidence.evaluator = Unavailable()
        result = self.complete()
        self.assertEqual(result.profile.onboarding_phase, 'complete')
        self.assertEqual(result.profile.evaluation_status, 'failed')
        self.assertIsNone(result.profile.estimates.reasoning.value)
        self.assertEqual(self.count(profile_evidence), 1)
        self.service.evidence.evaluator = self.evaluator
        retried = asyncio.run(self.service.calibration.retry_evaluation(A))
        self.assertEqual(retried.evaluation_status, 'applied')
        self.assertEqual(retried.estimates.reasoning.evidence_count, 2)

    def test_unsupported_or_fact_mutating_ai_output_is_rejected(self):
        class Invalid:
            async def evaluate(inner, evidence, context):
                result = (await self.evaluator.evaluate(evidence, context)).model_dump()
                result['education_level'] = 'high_school'
                return result
        self.service.evidence.evaluator = Invalid()
        result = self.complete()
        self.assertEqual(result.profile.details.education_level, EducationLevel.PRIMARY)
        self.assertEqual(result.profile.evaluation_status, 'failed')
        self.assertIsNone(result.profile.estimates.reasoning.value)
        class Unsupported:
            async def evaluate(inner, evidence, context):
                result = await self.evaluator.evaluate(evidence, context)
                result.reasoning.evidence_ids = ['not-a-real-item']
                return result
        self.service.evidence.evaluator = Unsupported()
        retried = asyncio.run(self.service.calibration.retry_evaluation(A))
        self.assertEqual(retried.evaluation_status, 'failed')

    def test_one_interaction_cannot_change_facts_or_dramatically_shift_estimates(self):
        result = self.complete()
        observation = EvidenceInput(source_type='interaction', source_id='high-school-textbook-discussion',
            occurred_at=datetime.now(timezone.utc), items=[EvidenceItem(id='reasoning-1', dimension='reasoning', correct=False, difficulty=.8)])
        evidence_id = self.service.evidence.record(A, observation)
        updated = asyncio.run(self.service.evidence.evaluate(A, evidence_id))
        self.assertEqual(updated.details, result.profile.details)
        self.assertLessEqual(abs(updated.estimates.reasoning.value - result.profile.estimates.reasoning.value), .0071)
        self.assertLessEqual(updated.estimates.reasoning.confidence - result.profile.estimates.reasoning.confidence, .05)
        self.assertEqual(self.service.evidence.record(A, observation), evidence_id)
        again = asyncio.run(self.service.evidence.evaluate(A, evidence_id))
        self.assertEqual(again, updated)
        with self.assertRaises(AppError):
            self.service.evidence.record(A, observation.model_copy(update={'items': [observation.items[0].model_copy(update={'correct': True})]}))

    def test_one_low_confidence_result_cannot_collapse_accumulated_confidence(self):
        result = self.complete()
        class LowConfidence:
            async def evaluate(inner, evidence, context):
                candidates = await self.evaluator.evaluate(evidence, context)
                candidates.reasoning.confidence = .01
                return candidates
        self.service.evidence.evaluator = LowConfidence()
        observation = EvidenceInput(source_type='interaction', source_id='uncertain-interaction', occurred_at=datetime.now(timezone.utc),
            items=[EvidenceItem(id='a', dimension='reasoning', correct=False)])
        identifier = self.service.evidence.record(A, observation)
        updated = asyncio.run(self.service.evidence.evaluate(A, identifier))
        self.assertGreaterEqual(updated.estimates.reasoning.confidence, result.profile.estimates.reasoning.confidence - .05)

    def test_fact_edits_invalidate_scope_but_preference_edits_preserve_estimates(self):
        result = self.complete()
        preferred = self.fill_details(learning_preference='concise', explanation_depth='brief')
        self.assertEqual(preferred.estimates, result.profile.estimates)
        self.assertEqual(preferred.context_version, result.profile.context_version)
        major = self.fill_details(field_of_study='History')
        self.assertEqual(major.estimates.reasoning, preferred.estimates.reasoning)
        self.assertIsNone(major.estimates.domain_familiarity.value)
        changed_level = self.fill_details(education_level='high_school', field_of_study='History')
        self.assertTrue(all(getattr(changed_level.estimates, dim).value is None for dim in DIMENSIONS))
        self.assertEqual(changed_level.onboarding_phase, 'complete')
        self.assertIsNone(self.service.calibration.get(A))

    def test_owner_scope_and_immutable_evidence_constraints(self):
        result = self.complete()
        self.fill_details(B)
        attempt = self.service.calibration.get(A)
        self.assertIsNone(self.service.calibration.get(B))
        with self.assertRaises(AppError) as error:
            self.service.calibration.answer(B, attempt.id, AnswerRequest(expected_version=attempt.version, question_id=attempt.questions[0].id, option_id='a'))
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(AppError):
            asyncio.run(self.service.evidence.evaluate(B, result.evidence_id))
        for operation in (update(profile_evidence).values(payload={}), delete(profile_evidence), text('TRUNCATE student_profile_evidence')):
            with self.assertRaises(DBAPIError):
                with self.db.engine.begin() as connection:
                    connection.execute(operation)
        for operation in (update(calibration_attempt).values(payload={}), delete(calibration_attempt), text('TRUNCATE student_calibration_attempt CASCADE')):
            with self.assertRaises(DBAPIError):
                with self.db.engine.begin() as connection:
                    connection.execute(operation)
        with self.assertRaises(IntegrityError):
            with self.db.engine.begin() as connection:
                connection.execute(profile_evidence.insert().values(id=str(uuid4()), learner_id=B,
                    calibration_attempt_id=attempt.id, context_version=1, source_type='onboarding_calibration', source_id='forged',
                    payload={}, status='pending', created_at=datetime.now(timezone.utc)))

    def test_concurrent_start_and_answers_are_consistent(self):
        self.fill_details()
        with ThreadPoolExecutor(max_workers=4) as pool:
            views = list(pool.map(lambda _: self.service.calibration.start(A), range(4)))
        self.assertEqual(len({view.id for view in views}), 1)
        self.assertEqual(self.count(calibration_attempt), 1)
        view = views[0]
        question = view.questions[0]
        def answer(option):
            try:
                return self.service.calibration.answer(A, view.id, AnswerRequest(expected_version=view.version, question_id=question.id, option_id=option.id))
            except AppError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(answer, question.options[:2]))
        self.assertEqual(sum(response is not None for response in responses), 1)

    def test_context_change_during_ai_call_rejects_stale_estimates(self):
        view = self.answer_all()
        class Changing:
            async def evaluate(inner, evidence, context):
                self.fill_details(education_level='high_school')
                return await self.evaluator.evaluate(evidence, context)
        self.service.evidence.evaluator = Changing()
        result = asyncio.run(self.service.calibration.complete(A, view.id, VersionRequest(expected_version=view.version)))
        self.assertEqual(result.profile.details.education_level, EducationLevel.HIGH)
        self.assertIsNone(result.profile.estimates.reasoning.value)
        with self.repository.transaction(A) as store:
            self.assertEqual(store.evidence(result.evidence_id).status, 'superseded')

    def test_duplicate_evaluations_use_one_claim_and_apply_once(self):
        view = self.answer_all()
        class Concurrent:
            async def evaluate(inner, evidence, context):
                # Another request sees the active lease and does not call the AI.
                pending = await self.service.evidence.evaluate(A, evidence.id)
                self.assertEqual(pending.evaluation_status, 'evaluating')
                return await self.evaluator.evaluate(evidence, context)
        self.service.evidence.evaluator = Concurrent()
        result = asyncio.run(self.service.calibration.complete(A, view.id, VersionRequest(expected_version=view.version)))
        self.assertEqual(len(self.evaluator.calls), 1)
        self.assertEqual(result.profile.estimates.overall_proficiency.evidence_count, 8)

    def test_unknown_dimensions_need_accumulated_independent_evidence(self):
        profile = self.fill_details()
        self.service.calibration.skip(A, VersionRequest(expected_version=profile.version))
        for index in range(3):
            observation = EvidenceInput(source_type='interaction', source_id=f'interaction-{index}', occurred_at=datetime.now(timezone.utc),
                items=[EvidenceItem(id=f'item-{index}', dimension='reasoning', correct=True)])
            identifier = self.service.evidence.record(A, observation)
            updated = asyncio.run(self.service.evidence.evaluate(A, identifier))
            if index < 2:
                self.assertIsNone(updated.estimates.reasoning.value)
        self.assertIsNotNone(updated.estimates.reasoning.value)
        self.assertLess(updated.estimates.reasoning.confidence, .2)
        self.assertIsNone(updated.estimates.quantitative.value)
        self.assertEqual(updated.details, details())

    def test_expired_evaluation_claim_can_be_retried_after_restart(self):
        profile = self.fill_details()
        self.service.calibration.skip(A, VersionRequest(expected_version=profile.version))
        observation = EvidenceInput(source_type='assessment', source_id='recoverable', occurred_at=datetime.now(timezone.utc),
            items=[EvidenceItem(id='a', dimension='reasoning', correct=True), EvidenceItem(id='b', dimension='reasoning', correct=False)])
        identifier = self.service.evidence.record(A, observation)
        with self.repository.transaction(A) as store:
            evidence = store.evidence(identifier)
            evidence.status, evidence.evaluation_token = 'evaluating', str(uuid4())
            evidence.claimed_at = datetime.now(timezone.utc) - timedelta(minutes=3)
            store.save_evidence(evidence)
        updated = asyncio.run(self.service.evidence.evaluate(A, identifier))
        self.assertEqual(updated.estimates.reasoning.evidence_count, 2)
        self.assertEqual(len(self.evaluator.calls), 1)

    def test_application_failure_rolls_back_estimates_and_can_recover_without_double_counting(self):
        from app.student_profile.repositories.store import PostgresProfileStore
        view = self.answer_all()
        save_evidence = PostgresProfileStore.save_evidence
        def fail_application(store, evidence, **kwargs):
            if evidence.status == 'applied':
                raise RuntimeError('Simulated persistence failure after saving estimates')
            return save_evidence(store, evidence, **kwargs)
        with patch.object(PostgresProfileStore, 'save_evidence', fail_application):
            with self.assertRaises(RuntimeError):
                asyncio.run(self.service.calibration.complete(A, view.id, VersionRequest(expected_version=view.version)))
        profile = self.service.get(A)
        self.assertEqual(profile.onboarding_phase, 'complete')
        self.assertEqual(profile.evaluation_status, 'evaluating')
        self.assertEqual(profile.estimates.overall_proficiency.evidence_count, 0)
        self.assertIsNone(profile.estimates.reasoning.value)
        with self.repository.transaction(A) as store:
            evidence = store.latest_calibration_evidence()
            self.assertEqual(evidence.status, 'evaluating')
            self.assertIsNone(evidence.evaluation)
            evidence.claimed_at = datetime.now(timezone.utc) - timedelta(minutes=3)
            store.save_evidence(evidence)
        recovered = asyncio.run(self.service.calibration.retry_evaluation(A))
        self.assertEqual(recovered.evaluation_status, 'applied')
        self.assertEqual(recovered.estimates.overall_proficiency.evidence_count, 8)
        self.assertEqual(self.count(profile_evidence), 1)
        self.assertEqual(asyncio.run(self.service.calibration.retry_evaluation(A)), recovered)

    def test_migrations_no_drift_and_profile_downgrade_preserves_accounts(self):
        self.fill_details()
        with self.db.engine.connect() as connection:
            command.check(migration_config(connection))
        with self.db.engine.begin() as connection:
            command.downgrade(migration_config(connection), '20261007_0002')
        upgrade(self.db.engine)
        self.assertEqual(self.service.get(A).onboarding_phase, 'information')
        with self.db.engine.connect() as connection:
            command.check(migration_config(connection))

    def test_real_api_auth_ownership_csrf_and_chat_onboarding_gate(self):
        application = FastAPI()
        application.state.auth_service = AuthService(PostgresIdentityRepository(self.db.sessions), ExternalTokenVerifier({}))
        application.state.student_profile_service = self.service
        class Chat:
            async def reply(self, *_):
                return 'Welcome'
        application.state.chat_service = Chat()
        register_exception_handlers(application)
        application.include_router(api_router)
        with TestClient(application, headers={'Origin': 'http://localhost:5173', 'X-Mentra-Session': 'cookie'}) as client:
            self.assertEqual(client.get('/api/v1/student-profile').status_code, 401)
            registration = client.post('/api/v1/auth/register', json={'username': 'profile_user', 'password': 'a long unique passphrase'})
            self.assertEqual(registration.status_code, 201)
            payload = {'messages': [{'role': 'user', 'content': 'Hello'}]}
            self.assertEqual(client.post('/api/v1/chat', json=payload).status_code, 409)
            initial = client.get('/api/v1/student-profile').json()
            request = {'expected_version': initial['version'], 'details': details().model_dump(mode='json')}
            self.assertEqual(client.put('/api/v1/student-profile/details', json=request, headers={'Origin': 'https://attacker.example'}).status_code, 403)
            self.assertEqual(client.put('/api/v1/student-profile/details', json=request | {'learner_id': A}).status_code, 422)
            updated = client.put('/api/v1/student-profile/details', json=request)
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(client.post('/api/v1/student-profile/calibration/skip', json={'expected_version': updated.json()['version']}).status_code, 200)
            self.assertEqual(client.post('/api/v1/chat', json=payload).status_code, 200)
