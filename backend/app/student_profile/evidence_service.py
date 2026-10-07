"""Persist evidence first; evaluate outside DB locks; apply once under ownership lock."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pydantic import ValidationError
from .errors import conflict, information_required, EvaluationUnavailable
from .schemas import EvidenceInput, ProfileEvidence, AIEvaluation
from .policy import context_packet, apply_estimates, POLICY_VERSION


class ProfileEvidenceService:
    def __init__(self, repository, evaluator, *, clock=lambda: datetime.now(timezone.utc)):
        self.repository, self.evaluator, self.clock = repository, evaluator, clock

    def record(self, learner_id: str, observation: EvidenceInput) -> str:
        """Trusted server integration only. No HTTP endpoint accepts these fields."""
        observation = EvidenceInput.model_validate(observation.model_dump())
        if observation.source_type == 'onboarding_calibration':
            raise ValueError('Calibration evidence must come from deterministic calibration scoring')
        if observation.occurred_at > self.clock() + timedelta(minutes=5):
            raise ValueError('Evidence cannot be dated in the future')
        with self.repository.transaction(learner_id) as store:
            profile = store.profile()
            if profile.details is None:
                raise information_required()
            existing = store.source_evidence(observation.source_type, observation.source_id)
            if existing:
                if existing.input != observation:
                    raise conflict('This evidence source was already recorded with different results.')
                return existing.id
            evidence = ProfileEvidence(id=str(uuid4()), learner_id=profile.learner_id,
                context_version=profile.context_version, details_snapshot=profile.details,
                input=observation, created_at=self.clock())
            store.save_evidence(evidence, new=True)
            return evidence.id

    async def evaluate(self, learner_id: str, evidence_id: str):
        now = self.clock()
        with self.repository.transaction(learner_id) as store:
            profile, evidence = store.profile(), store.evidence(evidence_id)
            if evidence is None:
                raise conflict('This evidence is not available for your profile.')
            if evidence.status in {'applied', 'superseded'}:
                return profile
            if evidence.context_version != profile.context_version:
                evidence.status = 'superseded'
                store.save_evidence(evidence)
                return profile
            if evidence.status == 'evaluating' and evidence.claimed_at and evidence.claimed_at > now - timedelta(minutes=2):
                return profile
            token = str(uuid4())
            evidence.status, evidence.evaluation_token, evidence.claimed_at = 'evaluating', token, now
            store.save_evidence(evidence)
            if evidence.input.source_type == 'onboarding_calibration':
                profile.evaluation_status, profile.updated_at = 'evaluating', now
                profile = store.save_profile(profile)
            context = context_packet(profile)
        try:
            evaluation = await asyncio.wait_for(self.evaluator.evaluate(evidence, context), timeout=45)
            evaluation = AIEvaluation.model_validate(evaluation)
            # Validate before entering the final transaction, including references.
            from .policy import validate_evaluation
            validate_evaluation(evaluation, evidence)
        except (EvaluationUnavailable, asyncio.TimeoutError, ValidationError):
            with self.repository.transaction(learner_id) as store:
                profile, saved = store.profile(), store.evidence(evidence_id)
                if saved.evaluation_token == token and saved.status == 'evaluating':
                    saved.status = 'failed' if saved.context_version == profile.context_version else 'superseded'
                    store.save_evidence(saved)
                    if saved.context_version == profile.context_version and saved.input.source_type == 'onboarding_calibration':
                        profile.evaluation_status, profile.updated_at = 'failed', self.clock()
                        profile = store.save_profile(profile)
                return profile
        with self.repository.transaction(learner_id) as store:
            profile, saved = store.profile(), store.evidence(evidence_id)
            if saved.evaluation_token != token or saved.status != 'evaluating':
                return profile
            if saved.context_version != profile.context_version:
                saved.status = 'superseded'
                store.save_evidence(saved)
                return profile
            profile.estimates = apply_estimates(profile.estimates, saved, evaluation)
            profile.updated_at = self.clock()
            if saved.input.source_type == 'onboarding_calibration':
                profile.evaluation_status = 'applied'
            profile = store.save_profile(profile)
            saved.status, saved.evaluation = 'applied', evaluation
            saved.policy_version, saved.applied_estimates = POLICY_VERSION, profile.estimates
            store.save_evidence(saved)
            return profile
