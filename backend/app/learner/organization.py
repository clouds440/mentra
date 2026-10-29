"""Provider-independent topic membership orchestration; no mastery writes."""
from dataclasses import replace
from hashlib import sha256

from app.core.exceptions import AppError
from .normalization import normalize
from .topics import LearningTopic, TopicPage, TopicSkillsPage, TopicOrganization, TopicSubskill


class _OrganizationChanged(Exception):
    pass


class TopicService:
    def __init__(self, engine, resolver):
        self.engine, self.repository, self.resolver = engine, engine.repository, resolver

    def page(self, request):
        contexts = self.engine.contexts.select(request.learner_id, request.context_ids)
        rows, total, ungrouped, offset = self.repository.topic_page(request.learner_id,
            [context.id for context in contexts], normalize(request.query), request.limit, request.offset)
        return TopicPage(items=[LearningTopic(**row) for row in rows], total=total,
            ungrouped_count=ungrouped, limit=request.limit, offset=offset, generated_at=self.engine.clock())

    def skills(self, request, topic_id):
        contexts = self.engine.contexts.select(request.learner_id, request.context_ids)
        from .exceptions import LearnerError
        try:
            topic, concepts, total, offset = self.repository.topic_skills(request.learner_id,
                [context.id for context in contexts], topic_id, normalize(request.query), request.limit, request.offset)
        except LearnerError as error:
            raise AppError('LEARNING_TOPIC_UNAVAILABLE', 'This learning topic is unavailable.', 404) from error
        topic = {key: value for key, value in topic.items() if key in LearningTopic.model_fields}
        items = self.engine.retrieval.project(request.learner_id, concepts, contexts)
        memberships = self.repository.skill_memberships(request.learner_id, [value.concept_id for value in items])
        descriptions = {value.id:value.description for value in concepts}
        items = [TopicSubskill(**value.model_dump(), ability=memberships.get(value.concept_id, {}).get('ability')
            or descriptions.get(value.concept_id)) for value in items]
        return TopicSkillsPage(topic=LearningTopic(**topic), items=items, total=total,
            limit=request.limit, offset=offset, generated_at=self.engine.clock())

    async def _advice(self, labels, topic, context, candidates, existing):
        from app.core.logging import workflow_logger
        for _ in range(2):
            try:
                result = TopicOrganization.model_validate(await self.resolver.organize(labels, topic, context, candidates, existing))
                if result.needs_wider_lookup and not result.placements:
                    return result
                if len(result.placements) != len(labels) or {value.label for value in result.placements} != set(labels):
                    raise ValueError('Incomplete topic organization')
                return result
            except Exception as error:
                # Explicit optional-provider boundary. A cancellation is a
                # BaseException and must propagate; no failure becomes a guess.
                workflow_logger.event('topic.organization_unavailable', error_type=type(error).__name__)
        return None

    async def _ungrouped(self, request, existing, published=False):
        from starlette.concurrency import run_in_threadpool
        def save():
            from .models import Concept
            from uuid import uuid4
            values = []
            with self.repository.transaction(learner_ids=[request.learner_id], ontology=True) as repository:
                self.engine.contexts.require(request.learner_id, request.context_id, repository)
                for label in request.labels:
                    identifier = existing.get(label)
                    if identifier:
                        concept = repository.get_concept(identifier)
                    else:
                        key = sha256(f'{request.learner_id}:{request.context_id}:{normalize(label)}'.encode()).hexdigest()[:24]
                        name = f'unclassified-{key}'
                        concept = repository.get_concept_by_normalized_name(name)
                        if not concept:
                            concept = Concept(str(uuid4()), name)
                            repository.create_concept(concept)
                    repository.save_ungrouped_skill(request.learner_id, concept.id, label)
                    if published:
                        repository.add_context_concept(request.context_id, concept.id, learner_id=request.learner_id)
                        repository.publish_topic_skills(request.learner_id, [concept.id])
                    values.append(replace(concept, canonical_name=label))
            return values
        return await run_in_threadpool(save)

    async def resolve(self, request, *, existing=None, published=False, preview=False, _retried=False, _bindings=False):
        from starlette.concurrency import run_in_threadpool
        context = await run_in_threadpool(self.engine.contexts.require, request.learner_id, request.context_id)
        if not self.resolver or not hasattr(self.resolver, 'organize'):
            raise AppError('LEARNING_ORGANIZATION_UNAVAILABLE', 'Topic organization is unavailable. Please try again.', 503)
        labels = list(dict.fromkeys(request.labels))
        known = await run_in_threadpool(self.repository.known_topic_labels, request.learner_id, request.context_id, labels, request.topic)
        if len(known) == len(labels) and not existing:
            if published:
                def publish():
                    with self.repository.transaction(learner_ids=[request.learner_id]) as repository:
                        repository.publish_topic_skills(request.learner_id, [value.id for value in known.values()])
                await run_in_threadpool(publish)
            values = {label: replace(known[label], canonical_name=label) for label in labels}
            return values if _bindings else list(values.values())
        if known and not existing:
            missing = await self.resolve(request.model_copy(update={'labels': [label for label in labels if label not in known]}), published=published, _bindings=True)
            values = {label:replace(known[label],canonical_name=label) if label in known else missing[label] for label in labels}
            return values if _bindings else list(values.values())
        version = await run_in_threadpool(self.repository.topic_registry_version, request.learner_id)
        candidates = await run_in_threadpool(self.repository.topic_candidates, request.learner_id,
            request.context_id, request.topic + ' ' + ' '.join(labels), 12)
        # Existing skills are supplied only by owned-context migration, never LLM IDs.
        existing = existing or {}
        result = await self._advice(labels, request.topic, context.name, candidates, existing)
        if result is None:
            if preview:
                raise AppError('LEARNING_ORGANIZATION_UNAVAILABLE', 'Grouping is temporarily unavailable. Your skills are unchanged.', 503)
            values = await self._ungrouped(request.model_copy(update={'labels':labels}), existing, published)
            return dict(zip(labels,values,strict=True)) if _bindings else values
        if result.needs_wider_lookup:
            expansion=' '.join(term[:200] for term in result.search_terms)
            candidates = await run_in_threadpool(self.repository.topic_candidates, request.learner_id,
                request.context_id, expansion + ' ' + request.topic + ' ' + ' '.join(labels), 24)
            result = await self._advice(labels, request.topic, context.name, candidates, existing)
        if result is None or result.needs_wider_lookup or any(value.action == 'defer' for value in result.placements):
            if preview:
                raise AppError('LEARNING_ORGANIZATION_UNAVAILABLE', 'These skills need clearer grouping. Your skills are unchanged.', 503)
            values = await self._ungrouped(request.model_copy(update={'labels':labels}), existing, published)
            return dict(zip(labels,values,strict=True)) if _bindings else values
        allowed_topics = {item['id'] for item in candidates}
        allowed_skills = {skill['concept_id']: item['id'] for item in candidates for skill in item['subskills']}
        for placement in result.placements:
            if placement.action == 'defer':
                raise AppError('LEARNING_ORGANIZATION_AMBIGUOUS', 'Add a little more subject context to identify these skills.', 422)
            if placement.topic_id and placement.topic_id not in allowed_topics:
                raise AppError('LEARNING_ORGANIZATION_INVALID', 'The selected learning topic is unavailable.', 502)
            if placement.topic_id:
                parent = next(item for item in candidates if item['id'] == placement.topic_id)
                placement.topic_name, placement.scope = parent['name'], parent['scope']
            if placement.skill_id:
                if placement.skill_id not in allowed_skills and placement.skill_id not in existing.values():
                    raise AppError('LEARNING_ORGANIZATION_INVALID', 'The selected subskill is unavailable.', 502)
                if placement.skill_id in allowed_skills and allowed_skills[placement.skill_id] != placement.topic_id:
                    raise AppError('LEARNING_ORGANIZATION_INVALID', 'Subskill membership changed. Please retry.', 409)
        if preview:
            def propose():
                with self.repository.transaction(learner_ids=[request.learner_id]) as repository:
                    identifier = repository.save_topic_proposal(request.learner_id, dict(
                        request=request.model_dump(mode='json'), result=result.model_dump(mode='json'), existing=existing))
                return dict(proposal_id=identifier, placements=[dict(topic_name=value.topic_name,
                    subskill_name=value.skill_name or value.label, scope=value.scope) for value in result.placements])
            return await run_in_threadpool(propose)
        def commit():
            concepts = {}
            with self.repository.transaction(learner_ids=[request.learner_id], ontology=True) as repository:
                if repository.topic_registry_version(request.learner_id) != version:
                    raise _OrganizationChanged()
                self.engine.contexts.require(request.learner_id, request.context_id, repository)
                for placement in result.placements:
                    skill_id = existing.get(placement.label) or placement.skill_id
                    if skill_id:
                        concept = repository.get_concept(repository.canonical_id(skill_id))
                    else:
                        # Scope new skills without making globally unique display
                        # labels establish cross-subject identity.
                        from .models import Concept
                        from uuid import uuid4
                        skill_name = placement.skill_name or placement.label
                        scope = normalize(placement.topic_name + ':' + placement.scope)
                        suffix = sha256(f'{request.learner_id}:{scope}:{normalize(skill_name)}'.encode()).hexdigest()[:24]
                        internal_name = f'skill-{suffix}'
                        concept = repository.get_concept_by_normalized_name(normalize(internal_name))
                        if not concept:
                            concept = Concept(str(uuid4()), internal_name)
                            repository.create_concept(concept)
                    repository.save_topic_membership(request.learner_id, request.context_id, concept.id,
                        placement, published=published)
                    if published:
                        repository.add_context_concept(request.context_id, concept.id, learner_id=request.learner_id)
                    concepts[placement.label] = replace(concept, canonical_name=placement.skill_name or placement.label)
                repository.save_skill_resolution_bindings(request.learner_id,request.context_id,request.topic,
                    {label:value.id for label,value in concepts.items()})
            return concepts
        try:
            values = await run_in_threadpool(commit)
            return values if _bindings else [values[label] for label in labels]
        except _OrganizationChanged:
            if _retried:
                raise AppError('LEARNING_ORGANIZATION_CHANGED', 'Your topics changed during organization. Please retry.', 409)
            return await self.resolve(request, existing=existing, published=published, preview=preview, _retried=True, _bindings=_bindings)

    async def organize_existing(self, owner, context_id, *, preview=False):
        from starlette.concurrency import run_in_threadpool
        from .schemas import GeneratedConceptsRequest
        context = await run_in_threadpool(self.engine.contexts.require, owner, context_id)
        concepts = await run_in_threadpool(self.repository.ungrouped_skills, owner, context_id, 10)
        if not concepts:
            return dict(organized=0)
        by_label = {concept.canonical_name: concept.id for concept in concepts}
        response = await self.resolve(GeneratedConceptsRequest(learner_id=owner, context_id=context_id,
            topic=context.name, labels=list(by_label)), existing=by_label, published=True, preview=preview)
        if preview:
            return response if isinstance(response, dict) else dict(organized=0, unresolved=len(by_label))
        memberships = await run_in_threadpool(self.repository.skill_memberships, owner, list(by_label.values()))
        count = sum(bool(value['topic_id']) for value in memberships.values())
        return dict(organized=count, unresolved=len(by_label) - count)

    def apply_proposal(self, owner, identifier, *, undo=False):
        from datetime import timedelta
        from .schemas import GeneratedConceptsRequest
        with self.repository.transaction(learner_ids=[owner]) as repository:
            proposal = repository.topic_proposal(owner, identifier)
            if not proposal:
                raise AppError('LEARNING_TOPIC_UNAVAILABLE', 'This grouping preview is unavailable.', 404)
            applied = repository.topic_change_receipt(owner, identifier, 'topic_organization_applied')
            reverted = repository.topic_change_receipt(owner, identifier, 'topic_organization_reverted')
            if undo:
                if reverted:
                    return dict(organized=0, reverted=True)
                if not applied:
                    raise AppError('REVISION_CONFLICT', 'This grouping has not been applied.', 409)
                from .exceptions import LearnerError
                try:
                    repository.ungroup_topic_skills(owner, applied['memberships'], applied.get('revisions'))
                except LearnerError as error:
                    raise AppError('REVISION_CONFLICT', 'These skills were regrouped. Refresh before changing them.', 409) from error
                repository.audit('topic_organization_reverted', dict(proposal_id=identifier), owner)
                return dict(organized=0, reverted=True)
            if applied:
                return dict(organized=0 if reverted else len(applied['memberships']), reverted=bool(reverted))
            if proposal['created_at'] + timedelta(days=1) < self.engine.clock():
                raise AppError('REVISION_CONFLICT', 'This preview expired. Prepare a new grouping.', 409)
            payload = proposal['details_json']
            request = GeneratedConceptsRequest.model_validate(payload['request'])
            self.engine.contexts.require(owner, request.context_id, repository)
            existing = payload['existing']
            current = repository.skill_memberships(owner, list(existing.values()))
            if any(value.get('topic_id') for value in current.values()):
                raise AppError('REVISION_CONFLICT', 'Some skills were already grouped. Prepare a new preview.', 409)
            for placement in TopicOrganization.model_validate(payload['result']).placements:
                repository.save_topic_membership(owner, request.context_id, existing[placement.label], placement, published=True)
            after = repository.skill_memberships(owner, list(existing.values()))
            repository.audit('topic_organization_applied', dict(proposal_id=identifier,
                memberships={key: value['topic_id'] for key, value in after.items()},
                revisions={value['topic_id']: value['revision'] for value in after.values()}), owner)
            return dict(organized=len(after), proposal_id=identifier)
