"""Single, atomic evidence ingestion path shared by every producer."""

from dataclasses import asdict, replace
from contextlib import nullcontext
from datetime import timedelta
from uuid import uuid4

from app.learner.exceptions import ConceptNotFoundError, InvalidEvidenceError
from app.learner.models import LearnerConceptState, LearningEvidence
from app.learner.schemas import (
    ConfirmEvidenceRequest, ContextActivityRequest, EvidenceSubmissionRequest, EvidenceSubmissionResult,
)


from app.core.logging import workflow_logger

@workflow_logger.connect_module(default_outcome='success')
class EvidenceService:
    def __init__(self, repository, contexts, mastery, retention, clock):
        self.repository, self.contexts = repository, contexts
        self.mastery, self.retention, self.clock = mastery, retention, clock

    def submit(self, request: EvidenceSubmissionRequest, repository=None) -> EvidenceSubmissionResult:
        request = EvidenceSubmissionRequest.model_validate(request.model_dump())
        if not request.source_id or not request.source_id.strip():
            raise InvalidEvidenceError('A stable source_id identifying the observation is required')
        if request.occurred_at > self.clock() + timedelta(minutes=5):
            raise InvalidEvidenceError('Evidence cannot occur in the future')
        with (nullcontext(repository) if repository is not None else self.repository.transaction()) as repository:
            repository.lock_learners([request.learner_id])
            canonical_id = repository.canonical_id(request.concept_id)
            if repository.get_concept(canonical_id) is None:
                raise ConceptNotFoundError(request.concept_id)
            if request.context_id:
                self.contexts.require(request.learner_id, request.context_id, repository)
            existing = repository.find_canonical_evidence_by_source(
                request.learner_id, request.source_type, request.source_id, canonical_id
            )
            if existing:
                # Retries may use a redirected identity but must not quietly overwrite content.
                incoming = request.model_dump(exclude={'concept_id'})
                if request.item_revision > 1 and not request.supersedes_evidence_id:
                    incoming['supersedes_evidence_id'] = existing.supersedes_evidence_id
                previous = {key: value for key, value in asdict(existing).items()
                            if key in incoming}
                if incoming != previous:
                    raise InvalidEvidenceError('Source ID was already used for a different observation')
                decision = repository.get_decision(existing.id, request.learner_id)
                state = repository.get_state(request.learner_id, canonical_id)
                return EvidenceSubmissionResult(evidence_id=existing.id, concept_id=canonical_id,
                       accepted=bool(decision and decision['status'] == 'ACCEPTED'), status='duplicate',
                       state_version=state.version if state else None,
                       verification_required=state.verification_required if state else False)
            if request.item_revision > 1 and (not request.item_id or not request.session_id):
                raise InvalidEvidenceError('Grading revisions require stable item and session identity')
            if request.item_id and request.session_id:
                prior = repository.latest_item_evidence(request.learner_id, canonical_id, request.item_id,
                                                       request.source_type, request.attempt_number or 1, request.session_id)
                if prior:
                    manual_original_correction = (request.item_revision == prior.item_revision == 1 and
                                                  request.supersedes_evidence_id == prior.id)
                    if prior.item_revision >= request.item_revision and not manual_original_correction:
                        raise InvalidEvidenceError('A newer or equal grading revision already exists')
                    if not request.supersedes_evidence_id:
                        request = request.model_copy(update={'supersedes_evidence_id': prior.id})
            if request.supersedes_evidence_id:
                self._validate_correction(repository, request.learner_id, canonical_id, request)
            evidence = LearningEvidence(id=str(uuid4()), **request.model_dump())
            evidence = replace(evidence, concept_id=canonical_id)
            # UNKNOWN chat observations remain auditable, but never imply mastery.
            extraction = evidence.extraction_confidence
            pending = ((extraction is not None and extraction < 0.8) or
                       (evidence.source_type == 'HANDWRITTEN_ASSESSMENT' and extraction is None) or
                       evidence.evidence_confidence < 0.5)
            repository.append_evidence(evidence)
            repository.save_decision(evidence.id, 'PENDING' if pending else 'ACCEPTED',
                                     'low_confidence' if pending else 'validated', request.learner_id)
            state = None
            if not pending:
                if evidence.supersedes_evidence_id:
                    repository.supersede_decision(evidence.supersedes_evidence_id, request.learner_id)
                    state = self.recompute(evidence.learner_id, canonical_id, repository)
                else:
                    state = self._apply(repository, evidence)
                if request.context_id:
                    repository.add_context_concept(request.context_id, canonical_id, learner_id=request.learner_id)
                    self.contexts.record_activity(ContextActivityRequest(learner_id=request.learner_id,
                                                  context_id=request.context_id, reason='accepted_evidence',
                                                  occurred_at=request.occurred_at), repository)
            repository.audit('evidence_pending' if pending else 'evidence_accepted',
                             {'evidence_id': evidence.id, 'source_type': evidence.source_type,
                              'policy': self.mastery.version, 'version': state.version if state else None,
                              'verification_required': state.verification_required if state else False},
                             request.learner_id, canonical_id)
            return EvidenceSubmissionResult(evidence_id=evidence.id, concept_id=canonical_id,
                   accepted=not pending, status='pending' if pending else 'accepted',
                   state_version=state.version if state else None,
                   verification_required=state.verification_required if state else False)

    def _validate_correction(self, repository, learner_id, concept_id, observation):
        supersedes_id = observation.supersedes_evidence_id
        original = repository.get_evidence(supersedes_id, learner_id)
        decision = repository.get_decision(supersedes_id, learner_id)
        if (not original or original.learner_id != learner_id or
                repository.canonical_id(original.concept_id) != concept_id or
                not decision or decision['status'] != 'ACCEPTED'):
            raise InvalidEvidenceError('A correction must supersede accepted evidence for the same student and concept')
        for field in ('item_id', 'session_id', 'attempt_number'):
            previous, incoming = getattr(original, field), getattr(observation, field)
            if previous is not None and incoming is not None and previous != incoming:
                raise InvalidEvidenceError('A correction must preserve item, session and attempt identity')

    def _apply(self, repository, evidence: LearningEvidence) -> LearnerConceptState | None:
        old = repository.get_state(evidence.learner_id, evidence.concept_id)
        confidence_version = getattr(getattr(self.mastery, 'confidence_policy', None), 'version', None)
        if old and (old.mastery_policy_version != self.mastery.version or
                    old.policy_data.get('policy_identity', self.mastery.version) != getattr(self.mastery, 'identity', self.mastery.version) or
                    (confidence_version is not None and old.policy_data.get('confidence_version') != confidence_version) or
                    (old.last_evidence_at and old.last_evidence_at > evidence.occurred_at)):
            return self.recompute(evidence.learner_id, evidence.concept_id, repository)
        state = old or LearnerConceptState(evidence.learner_id, evidence.concept_id)
        updated = self.mastery.update(state, evidence)
        if updated is state:
            return old
        updated = replace(updated, version=state.version + 1, retention_policy_version=self.retention.version)
        repository.save_state(updated)
        return updated

    def recompute(self, learner_id: str, concept_id: str, repository=None) -> LearnerConceptState | None:
        if repository is None:
            with self.repository.transaction(learner_ids=[learner_id]) as transaction:
                return self.recompute(learner_id, transaction.canonical_id(concept_id), transaction)
        old = repository.get_state(learner_id, concept_id)
        state = LearnerConceptState(learner_id, concept_id)
        for evidence in repository.accepted_evidence(learner_id, concept_id):
            state = self.mastery.update(state, replace(evidence, concept_id=concept_id))
        if state.evidence_count == 0 and old is None:
            return None
        policy_data = dict(state.policy_data, policy_identity=getattr(self.mastery, 'identity', self.mastery.version))
        state = replace(state, version=(old.version if old else 0) + 1, policy_data=policy_data,
                        mastery_policy_version=self.mastery.version,
                        retention_policy_version=self.retention.version)
        repository.save_state(state)
        repository.audit('state_recomputed', {'policy': self.mastery.version, 'version': state.version,
                                             'evidence_count': state.evidence_count}, learner_id, concept_id)
        return state

    def confirm(self, request: ConfirmEvidenceRequest, repository=None) -> EvidenceSubmissionResult:
        context = nullcontext(repository) if repository is not None else self.repository.transaction(learner_ids=[request.learner_id])
        with context as repository:
            evidence = repository.get_evidence(request.evidence_id, request.learner_id)
            if evidence is None or evidence.learner_id != request.learner_id:
                raise InvalidEvidenceError('Pending observation not found')
            decision = repository.get_decision(evidence.id, request.learner_id)
            canonical_id = repository.canonical_id(evidence.concept_id)
            if decision and decision['status'] == 'ACCEPTED' and decision['confirmed_at']:
                state = repository.get_state(request.learner_id, canonical_id)
                return EvidenceSubmissionResult(evidence_id=evidence.id, concept_id=canonical_id,
                       accepted=True, status='duplicate', state_version=state.version if state else None,
                       verification_required=state.verification_required if state else False)
            if not decision or decision['status'] != 'PENDING' or decision['reason'] != 'low_confidence':
                raise InvalidEvidenceError('Observation is not pending confirmation')
            # Confirming transcription cannot override an uncertain grade.
            if (evidence.evidence_confidence or 0) < 0.5:
                raise InvalidEvidenceError('The uncertain grade must be reassessed as a new observation')
            if evidence.item_id and evidence.session_id:
                latest = repository.latest_item_evidence(request.learner_id, canonical_id, evidence.item_id,
                    evidence.source_type, evidence.attempt_number or 1, evidence.session_id)
                if latest and latest.id != evidence.supersedes_evidence_id:
                    raise InvalidEvidenceError('A newer or equal accepted observation already exists for this item')
            if evidence.supersedes_evidence_id:
                self._validate_correction(repository, request.learner_id, canonical_id, evidence)
                repository.supersede_decision(evidence.supersedes_evidence_id, request.learner_id)
            repository.confirm_decision(evidence.id, request.confirmation_source, request.learner_id)
            state = self.recompute(request.learner_id, canonical_id, repository)
            if evidence.context_id:
                repository.add_context_concept(evidence.context_id, canonical_id, learner_id=evidence.learner_id)
                self.contexts.record_activity(ContextActivityRequest(learner_id=request.learner_id,
                                              context_id=evidence.context_id, reason='confirmed_evidence',
                                              occurred_at=evidence.occurred_at), repository)
            repository.audit('transcription_confirmed', {'evidence_id': evidence.id,
                             'confirmation_source': request.confirmation_source}, request.learner_id, canonical_id)
            return EvidenceSubmissionResult(evidence_id=evidence.id, accepted=True, status='accepted',
                   concept_id=canonical_id, state_version=state.version if state else None,
                   verification_required=state.verification_required if state else False)
