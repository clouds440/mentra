from datetime import datetime, timezone
from uuid import uuid4
from app.core.exceptions import AppError
from ..errors import conflict, information_required
from ..schemas import CalibrationAttempt, ProfileEvidence, CalibrationResult
from .blueprints import blueprint
from .scoring import public_attempt, score


class CalibrationService:
    def __init__(self, repository, evidence_service, *, clock=lambda: datetime.now(timezone.utc)):
        self.repository, self.evidence_service, self.clock = repository, evidence_service, clock

    @staticmethod
    def _owned(store, attempt_id):
        attempt = store.attempt(attempt_id)
        if attempt is None:
            raise AppError('CALIBRATION_NOT_FOUND', 'This assessment is not available.', 404)
        if attempt.context_version != store.profile().context_version or attempt.status in {'skipped', 'superseded'}:
            raise conflict('Your profile changed. Start a new calibration assessment.')
        return attempt

    def get(self, learner_id):
        with self.repository.transaction(learner_id) as store:
            attempt = store.latest_attempt()
            if attempt and attempt.context_version == store.profile().context_version and attempt.status in {'in_progress', 'completed'}:
                return public_attempt(attempt)
            return None

    def start(self, learner_id):
        with self.repository.transaction(learner_id) as store:
            profile = store.profile()
            if profile.details is None:
                raise information_required()
            latest = store.latest_attempt()
            if latest and latest.context_version == profile.context_version and latest.status in {'in_progress', 'completed'}:
                return public_attempt(latest)
            attempt_id = str(uuid4())
            version, questions = blueprint(profile.details, attempt_id)
            attempt = CalibrationAttempt(id=attempt_id, learner_id=profile.learner_id,
                blueprint_version=version, context_version=profile.context_version,
                details_snapshot=profile.details, questions=questions, created_at=self.clock())
            store.save_attempt(attempt, new=True)
            profile.calibration_status, profile.updated_at = 'in_progress', self.clock()
            store.save_profile(profile)
            return public_attempt(attempt)

    def answer(self, learner_id, attempt_id, request):
        with self.repository.transaction(learner_id) as store:
            attempt = self._owned(store, attempt_id)
            if attempt.status != 'in_progress':
                raise conflict('This assessment has already been completed.')
            question = next((item for item in attempt.questions if item.id == request.question_id), None)
            if question is None or request.option_id not in {option.id for option in question.options}:
                raise AppError('INVALID_CALIBRATION_ANSWER', 'Choose an available answer for this question.', 422)
            if attempt.answers.get(question.id) == request.option_id:
                return public_attempt(attempt)
            if request.expected_version != attempt.version:
                raise conflict('Your assessment changed elsewhere. Reload it and try again.')
            attempt.answers[question.id] = request.option_id
            return public_attempt(store.save_attempt(attempt))

    async def complete(self, learner_id, attempt_id, request):
        with self.repository.transaction(learner_id) as store:
            profile, attempt = store.profile(), self._owned(store, attempt_id)
            evidence = store.source_evidence('onboarding_calibration', attempt.id)
            if attempt.status == 'in_progress':
                if request.expected_version != attempt.version:
                    raise conflict('Your assessment changed elsewhere. Reload it and try again.')
                try:
                    observation = score(attempt, self.clock())
                except ValueError as exc:
                    raise AppError('CALIBRATION_INCOMPLETE', 'Answer all eight questions before finishing.', 422) from exc
                evidence = ProfileEvidence(id=str(uuid4()), learner_id=profile.learner_id,
                    calibration_attempt_id=attempt.id, context_version=attempt.context_version,
                    details_snapshot=attempt.details_snapshot, input=observation, created_at=self.clock())
                store.save_evidence(evidence, new=True)
                attempt.status, attempt.completed_at = 'completed', self.clock()
                store.save_attempt(attempt)
                profile.onboarding_phase, profile.calibration_status = 'complete', 'completed'
                profile.evaluation_status, profile.updated_at = 'pending', self.clock()
                profile = store.save_profile(profile)
        if evidence.status in {'pending', 'evaluating'}:
            profile = await self.evidence_service.evaluate(learner_id, evidence.id)
        return CalibrationResult(profile=profile, evidence_id=evidence.id)

    def skip(self, learner_id, request):
        with self.repository.transaction(learner_id) as store:
            profile = store.profile()
            if profile.details is None:
                raise information_required()
            if profile.calibration_status == 'skipped':
                return profile
            if profile.version != request.expected_version:
                raise conflict()
            if profile.calibration_status == 'completed':
                raise conflict('Your calibration is already complete.')
            attempt = store.latest_attempt()
            if attempt and attempt.status == 'in_progress':
                attempt.status, attempt.completed_at = 'skipped', self.clock()
                store.save_attempt(attempt)
            profile.onboarding_phase, profile.calibration_status = 'complete', 'skipped'
            profile.updated_at = self.clock()
            return store.save_profile(profile)

    async def retry_evaluation(self, learner_id):
        with self.repository.transaction(learner_id) as store:
            profile, evidence = store.profile(), store.latest_calibration_evidence()
            if evidence is None or evidence.context_version != profile.context_version:
                raise conflict('Complete a calibration assessment before evaluating it.')
        return await self.evidence_service.evaluate(learner_id, evidence.id)
