"""Correction-safe, conservative profile projection from accepted observations.

Domain familiarity is supported by subject answers; reasoning/comprehension and
quantitative ability require dedicated evidence and are never inferred here.
This deterministic adapter runs in the producer's owner transaction, without AI.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from app.learner.repositories.tables import learning_evidence as e, evidence_decision as d
from app.student_profile.repositories.tables import student_profile, profile_evidence
from app.student_profile.repositories.store import PostgresProfileStore
from app.student_profile.schemas import Estimates, EvidenceInput, EvidenceItem, ProfileEvidence, AIEvaluation, DIMENSIONS
from app.student_profile.policy import apply_estimates

POLICY = 'learning-profile-projection-v1'


def project_learning_profile(unit_of_work, owner):
    session = unit_of_work._session
    row = session.execute(select(student_profile).where(student_profile.c.learner_id == owner)).mappings().first()
    if not row or row['details'] is None:
        return  # Learning must work even before a profile exists.
    now = datetime.now(timezone.utc)
    store = PostgresProfileStore(session, owner, now)
    profile = store.profile()
    # Rebuild the baseline from legitimate profile evidence, excluding previous
    # projections. Repeated reads/corrections must never add cumulative weight.
    baseline = Estimates()
    rows = session.execute(select(profile_evidence).where(profile_evidence.c.learner_id == owner,
        profile_evidence.c.context_version == profile.context_version, profile_evidence.c.status == 'applied',
        profile_evidence.c.policy_version != POLICY).order_by(profile_evidence.c.created_at, profile_evidence.c.id)).mappings()
    for record in rows:
        evidence = store._evidence(record)
        baseline = apply_estimates(baseline, evidence, evidence.evaluation)
    # Window by item rather than concept: multi-concept questions count once.
    recent = session.execute(select(e).join(d, d.c.evidence_id == e.c.id).where(e.c.learner_id == owner,
        d.c.learner_id == owner, d.c.status == 'ACCEPTED', e.c.evidence_confidence >= .8,
        e.c.metadata_json['profile_context_version'].as_integer() == profile.context_version,
        e.c.source_type.in_(['QUIZ','CALIBRATION','HANDWRITTEN_ASSESSMENT','CHAT']))
        .order_by(e.c.occurred_at.desc(), d.c.sequence.desc()).limit(160)).mappings().all()
    selected, groups = [], {}
    for record in recent:
        key = (record['session_id'], record['item_id'])
        if record['score'] is None or not record['max_score']: continue
        if key not in groups:
            if len(groups) == 32: continue
            groups[key] = []
            selected.append(record)
        groups[key].append(record)
    if selected:
        items = []
        for record in selected:
            group = groups[(record['session_id'], record['item_id'])]
            # A question counts once, using its overall grade. Legacy evidence
            # without that metadata must agree across its accepted concepts.
            correct = all(item['metadata_json'].get('question_score', item['score']) ==
                item['metadata_json'].get('question_max_score', item['max_score']) for item in group)
            identity = hashlib.sha256(':'.join(sorted(str(item['id']) for item in group)).encode()).hexdigest()
            items.append(EvidenceItem(id=identity, dimension='domain_familiarity',
                correct=correct, difficulty=record['difficulty']))
        observation = EvidenceInput(source_type='assessment', source_id=f'learning:{profile.context_version}:' + hashlib.sha256(
            json.dumps(dict(items=[item.model_dump(mode='json') for item in items], baseline=baseline.domain_familiarity.model_dump(mode='json')), sort_keys=True).encode()).hexdigest(),
            occurred_at=max(record['occurred_at'] for record in selected), items=items, reliability=.35)
        unknown = dict(value=None, confidence=0, evidence_ids=[], rationale='No supporting task-specific evidence.')
        candidates = {dimension:dict(unknown) for dimension in DIMENSIONS}
        value = sum(item.correct for item in items) / len(items)
        for dimension in ('domain_familiarity',):
            candidates[dimension] = dict(value=value, confidence=.35, evidence_ids=[item.id for item in items],
                rationale='Conservative subject-answer evidence; assistance may be unknown.')
        evaluation = AIEvaluation(**candidates)
        identifier = str(uuid5(NAMESPACE_URL, f'{owner}:{profile.context_version}:{observation.source_id}'))
        evidence = ProfileEvidence(id=identifier, learner_id=owner, context_version=profile.context_version,
            details_snapshot=profile.details, input=observation, created_at=now)
        estimates = apply_estimates(baseline, evidence, evaluation)
        for dimension in DIMENSIONS:
            if dimension != 'domain_familiarity':
                setattr(estimates, dimension, getattr(profile.estimates, dimension).model_copy(deep=True))
        evidence.status, evidence.evaluation = 'applied', evaluation
        evidence.policy_version, evidence.applied_estimates = POLICY, estimates
        existing = store.source_evidence(observation.source_type, observation.source_id)
        if existing and existing.context_version != profile.context_version:
            # Source identity includes the education context to avoid reusing an
            # immutable snapshot after a profile context change.
            return
        # Applied profile evidence is immutable, including its status. Keep old
        # projections as historical snapshots; canonical decisions determine the
        # current projection. Replays never rewrite an applied snapshot.
        if existing is None: store.save_evidence(evidence, new=True)
    else:
        estimates = baseline
    # Subject answers do not establish general proficiency or reasoning ability.
    # Preserve those estimates even after field/context changes and corrections.
    for dimension in DIMENSIONS:
        if dimension != 'domain_familiarity':
            setattr(estimates, dimension, getattr(profile.estimates, dimension).model_copy(deep=True))
    if estimates != profile.estimates:
        profile.estimates, profile.updated_at = estimates, now
        store.save_profile(profile)
