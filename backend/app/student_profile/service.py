from datetime import datetime, timezone
from .schemas import ProfileUpdate, Estimates, Estimate
from .errors import conflict
from .evidence_service import ProfileEvidenceService
from .calibration.service import CalibrationService
from .policy import context_packet


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class StudentProfileService:
    def __init__(self, repository, evaluator, *, clock=lambda: datetime.now(timezone.utc)):
        self.repository, self.clock = repository, clock
        self.evidence = ProfileEvidenceService(repository, evaluator, clock=clock)
        self.calibration = CalibrationService(repository, self.evidence, clock=clock)

    def get(self, learner_id):
        return self.repository.read_profile(learner_id)

    def update_details(self, learner_id, request: ProfileUpdate):
        request = ProfileUpdate.model_validate(request.model_dump(exclude_unset=True))
        with self.repository.transaction(learner_id) as store:
            profile = store.profile()
            # Older callers omit this optional field; only an explicit blank/null clears it.
            if profile.details:
                # Old clients must not erase newer preferences they cannot edit.
                preserved = {key: getattr(profile.details, key) for key in
                             ('preferred_name', 'participation', 'visual_support', 'learning_purpose')
                             if key not in request.details.model_fields_set}
                request.details = request.details.model_copy(update=preserved)
            if profile.version != request.expected_version:
                # A lost response retry with identical details is harmless.
                if profile.details == request.details:
                    return profile
                raise conflict()
            return self._save_details(store, profile, request.details, 'user')

    def _save_details(self, store, profile, details, source):
        old = profile.details
        changed_level = old is None or old.education_level != details.education_level
        changed_field = old is None or old.field_of_study.casefold() != details.field_of_study.casefold()
        if changed_level or changed_field:
            profile.context_version += 1
            profile.estimates = Estimates() if changed_level else profile.estimates.model_copy(update={'domain_familiarity': Estimate()})
            profile.calibration_status, profile.evaluation_status = 'not_started', 'not_started'
            attempt = store.latest_attempt()
            if attempt and attempt.status == 'in_progress':
                attempt.status, attempt.completed_at = 'superseded', self.clock()
                store.save_attempt(attempt)
        profile.details, profile.details_source = details, source
        if profile.onboarding_phase == 'information':
            profile.onboarding_phase = 'calibration'
        profile.updated_at = self.clock()
        return store.save_profile(profile)

    def prompt_context(self, learner_id):
        profile = self.get(learner_id)
        workflow_logger.event('profile.context', profile_version=profile.version,
                              context_version=profile.context_version)
        return context_packet(profile)
