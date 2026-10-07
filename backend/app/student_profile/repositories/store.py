"""Transaction-bound, learner-scoped profile queries. No scoring/AI logic here."""
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from ..schemas import StudentProfile, CalibrationAttempt, ProfileEvidence
from ..errors import conflict
from .tables import student_profile, calibration_attempt, profile_evidence


class PostgresProfileStore:
    def __init__(self, session, learner_id, now):
        self.session, self.learner_id = session, learner_id
        initial = StudentProfile(learner_id=learner_id, created_at=now, updated_at=now)
        data = initial.model_dump(mode='json')
        data['created_at'] = data['updated_at'] = now
        session.execute(insert(student_profile).values(**data).on_conflict_do_nothing())

    def profile(self):
        row = self.session.execute(select(student_profile).where(student_profile.c.learner_id == self.learner_id)).mappings().one()
        return StudentProfile.model_validate(dict(row))

    def save_profile(self, profile):
        if profile.learner_id != self.learner_id:
            raise ValueError('Profile owner mismatch')
        data = profile.model_dump(mode='json', exclude={'learner_id', 'version', 'created_at'})
        # SQLAlchemy DateTime needs native datetime, not JSON strings.
        data['updated_at'] = profile.updated_at
        changed = self.session.execute(update(student_profile).where(student_profile.c.learner_id == self.learner_id,
            student_profile.c.version == profile.version).values(**data, version=profile.version + 1))
        if changed.rowcount != 1:
            raise conflict()
        return profile.model_copy(update={'version': profile.version + 1})

    @staticmethod
    def _attempt(row):
        if row is None:
            return None
        data = dict(row)
        payload = data.pop('payload')
        return CalibrationAttempt.model_validate(data | payload)

    def latest_attempt(self):
        return self._attempt(self.session.execute(select(calibration_attempt).where(
            calibration_attempt.c.learner_id == self.learner_id).order_by(calibration_attempt.c.created_at.desc(), calibration_attempt.c.id.desc()).limit(1)).mappings().first())

    def attempt(self, attempt_id):
        return self._attempt(self.session.execute(select(calibration_attempt).where(
            calibration_attempt.c.learner_id == self.learner_id, calibration_attempt.c.id == attempt_id)).mappings().first())

    def save_attempt(self, attempt, *, new=False):
        if attempt.learner_id != self.learner_id:
            raise ValueError('Attempt owner mismatch')
        data = attempt.model_dump(exclude={'details_snapshot', 'questions', 'answers'})
        data['payload'] = attempt.model_dump(mode='json', include={'details_snapshot', 'questions', 'answers'})
        if new:
            self.session.execute(calibration_attempt.insert().values(**data))
            return attempt
        data.pop('id')
        data['version'] = attempt.version + 1
        changed = self.session.execute(update(calibration_attempt).where(calibration_attempt.c.learner_id == self.learner_id,
            calibration_attempt.c.id == attempt.id, calibration_attempt.c.version == attempt.version).values(**data))
        if changed.rowcount != 1:
            raise conflict('Your assessment changed elsewhere. Reload it and try again.')
        return attempt.model_copy(update={'version': attempt.version + 1})

    @staticmethod
    def _evidence(row):
        if row is None:
            return None
        data = dict(row)
        payload = data.pop('payload')
        data.pop('source_type')
        data.pop('source_id')
        return ProfileEvidence.model_validate(data | payload)

    def evidence(self, evidence_id):
        return self._evidence(self.session.execute(select(profile_evidence).where(profile_evidence.c.learner_id == self.learner_id,
            profile_evidence.c.id == evidence_id)).mappings().first())

    def source_evidence(self, source_type, source_id):
        return self._evidence(self.session.execute(select(profile_evidence).where(profile_evidence.c.learner_id == self.learner_id,
            profile_evidence.c.source_type == source_type, profile_evidence.c.source_id == source_id)).mappings().first())

    def latest_calibration_evidence(self):
        return self._evidence(self.session.execute(select(profile_evidence).where(profile_evidence.c.learner_id == self.learner_id,
            profile_evidence.c.source_type == 'onboarding_calibration').order_by(profile_evidence.c.created_at.desc(), profile_evidence.c.id.desc()).limit(1)).mappings().first())

    def save_evidence(self, evidence, *, new=False):
        if evidence.learner_id != self.learner_id:
            raise ValueError('Evidence owner mismatch')
        data = evidence.model_dump(mode='json', exclude={'details_snapshot', 'input'})
        data['created_at'], data['claimed_at'] = evidence.created_at, evidence.claimed_at
        if new:
            data.update(source_type=evidence.input.source_type, source_id=evidence.input.source_id,
                payload=evidence.model_dump(mode='json', include={'details_snapshot', 'input'}))
            self.session.execute(profile_evidence.insert().values(**data))
        else:
            # Observation payload/identity/context are immutable even during retry.
            data = {key: data[key] for key in ('status', 'evaluation_token', 'claimed_at', 'evaluation', 'policy_version', 'applied_estimates')}
            self.session.execute(update(profile_evidence).where(profile_evidence.c.learner_id == self.learner_id,
                profile_evidence.c.id == evidence.id).values(**data))
